import math

from pyteal import *
from typing import Literal
from util import *
from src.config import *
from algosdk.v2client import algod

# -----    Subroutines    -----

# closeAccountTo(account: Expr) -> Expr:
#  Sends remaining balance of the application account to a specified account, i.e. it closes the application account.
#  Fee for the inner transaction is set to zero, thus fee pooling needs to be used.
#
@Subroutine(TealType.none)
def closeAccountTo(account: Expr) -> Expr:
    return If(Balance(Global.current_application_address()) != Int(0)).Then(
        Seq(
            InnerTxnBuilder.Begin(),
            InnerTxnBuilder.SetFields(
                {
                    TxnField.fee: Int(0),
                    TxnField.type_enum: TxnType.Payment,
                    TxnField.close_remainder_to: account,
                }
            ),
            InnerTxnBuilder.Submit(),
        )
    )

# payTo(account: Expr, amount: Expr) -> Expr:
#  Sends a payment transaction of amount to account
#
@Subroutine(TealType.none)
def payTo(account: Expr, amount: Expr) -> Expr:
    return Seq(
            InnerTxnBuilder.Begin(),
            InnerTxnBuilder.SetFields(
                {
                    TxnField.fee: Int(0),
                    TxnField.type_enum: TxnType.Payment,
                    TxnField.receiver: account,
                    TxnField.amount: amount
                }
            ),
            InnerTxnBuilder.Submit(),
        )


# -----   On close out    -----

# Escrow contract belonging to the sender
ec_id = App.localGet(Txn.sender(), MC_escrow_id_local_key)
# Get the number of proposals the escrow supports
ec_nsp = App.globalGetEx(ec_id, EC_num_support_props_key)
# Get the owner of the escrow
ec_owner = App.globalGetEx(ec_id, EC_owner_key)

on_close_out = Seq(
    ec_nsp,
    Assert(ec_nsp.hasValue()),
    ec_owner,
    Assert(ec_owner.hasValue()),
    # Close out can be done only if escrow has removed support from all proposals
    If(
        ec_nsp.value() == Int(0)
    ).Then(
        Seq(
            # Escrow is not supporting any more proposals and can be deleted
            InnerTxnBuilder.Begin(),
            InnerTxnBuilder.SetFields(
                {
                    TxnField.type_enum: TxnType.ApplicationCall,
                    TxnField.application_id: ec_id,
                    TxnField.on_completion: OnComplete.DeleteApplication,
                    TxnField.accounts: [ec_owner.value()],
                    TxnField.fee: Int(0),
                }
            ),
            InnerTxnBuilder.Submit(),
            Approve()
        )
    )
    .Else(
        Reject()
    )
)


# -----    On opt in      -----
# When opting in, a new escrow contract is created. The opting account must cover the increase in the required balance
# for the manager contract
escrow_funding_txn_index = Txn.group_index() - Int(1)

on_opt_in = Seq(
    If(
        Txn.sender() == Global.creator_address()
    ).Then(
        # Creator address can opt in without creation of an escrow
        Approve(),
    )
    .Else(
        # Every other address needs to create an escrow
        Seq(
            # Assert there is funding being received for the new escrow
            #  The transaction has to be a payment
            Assert(Gtxn[escrow_funding_txn_index].type_enum() == TxnType.Payment),
            #  The transaction has to be to this application address
            Assert(Gtxn[escrow_funding_txn_index].receiver() == Global.current_application_address()),
            #  The amount needs to be large enough
            Assert(Gtxn[escrow_funding_txn_index].amount() >= Int(EC_FUNDING_FOR_CREATION)),

            # Create the new escrow by calling create_app method of EscrowContract
            InnerTxnBuilder.Begin(),
            InnerTxnBuilder.SetFields(
                {
                    TxnField.type_enum: TxnType.ApplicationCall,
                    TxnField.application_args: [
                        Bytes(EC_contract.get_method_by_name("create_app").get_selector()),
                        Txn.sender(),
                    ],
                    TxnField.approval_program: Bytes("base64", EC_approval_program),
                    TxnField.clear_state_program: Bytes("base64", EC_clear_state_program),
                    TxnField.global_num_uints: Int(EC_NUM_GLOBAL_UINT),
                    TxnField.global_num_byte_slices: Int(EC_NUM_GLOBAL_BYTES),
                    TxnField.local_num_uints: Int(EC_NUM_LOCAL_UINT),
                    TxnField.local_num_byte_slices: Int(EC_NUM_LOCAL_BYTES),
                    TxnField.extra_program_pages: Int(EC_ExtraProgramPages),
                    TxnField.fee: Int(0),
                }
            ),
            InnerTxnBuilder.Submit(),

            # Store the ID of created escrow in local storage of user
            App.localPut(Txn.sender(), MC_escrow_id_local_key, InnerTxn.created_application_id()),
            Approve()
        )
    ),
)

# -----       Router      -----

def getRouter():

    # Main router class
    router = Router(
        # Name of the contract
        "ManagerContract",
        # What to do for each on-complete type when no arguments are passed (bare call)
        BareCallActions(
            # Updating the contract is not allowed
            update_application=OnCompleteAction.always(Reject()),
            # Deleting the contract is not allowed
            delete_application=OnCompleteAction.always(Reject()),
            # Closing out is allowed in certain cases
            close_out=OnCompleteAction.call_only(on_close_out),
            # Clearing the state is discouraged because will lose funds
            clear_state=OnCompleteAction.call_only(Reject()),
            # Opt-in is always allowed but requires some logic to execute first
            opt_in=OnCompleteAction.call_only(on_opt_in),
        ),
    )


    @router.method(no_op=CallConfig.CREATE)
    def create_app(commitLimit: abi.Uint64, frozenDuration: abi.Uint64, lockingDuration: abi.Uint64,
                   clawbackPercentage: abi.Uint64, passRewards: abi.Uint64):

        return Seq(
            # Set global variables
            App.globalPut(MC_commitment_limit_key, commitLimit.get()),
            App.globalPut(MC_frozen_duration_key, frozenDuration.get()),
            App.globalPut(MC_locking_duration_key, lockingDuration.get()),
            App.globalPut(MC_clawback_percentage_key, clawbackPercentage.get()),
            App.globalPut(MC_pass_rewards_key, passRewards.get()),
            # Initialize remaining global variables
            App.globalPut(MC_allow_optin_to_P_key, Int(OPTIN_NOT_ALLOWED)),
            Approve()
        )


    @router.method(no_op=CallConfig.CALL)
    def new_proposal(hash: abi.StaticBytes[Literal[32]], *, output: abi.Uint64) -> Expr:

        # Request for a new proposal needs to be accompanied by a funding transaction (i.e. to increase the balance of
        # the contract account to cover the increased required minimal balance due to it creating and opting into
        # another contract)
        prop_funding_txn_index = Txn.group_index() - Int(1)

        return Seq(
            # Assert correct length of ABI compound type for hash of proposal
            Assert(Len(hash.get()) == Int(32)),
            # Assert there is funding being received for the new proposal
            #  The transaction has to be a payment
            Assert(Gtxn[prop_funding_txn_index].type_enum() == TxnType.Payment),
            #  The transaction has to be to this application address
            Assert(Gtxn[prop_funding_txn_index].receiver() == Global.current_application_address()),
            #  The amount needs to be large enough
            Assert(Gtxn[prop_funding_txn_index].amount() >= Int(SC_FUNDING_FOR_CREATION + SC_FUNDING_FOR_OPTIN)),

            # Create the new proposal by calling create_app method of StakingContract
            InnerTxnBuilder.Begin(),
            InnerTxnBuilder.SetFields(
                {
                    TxnField.type_enum: TxnType.ApplicationCall,
                    TxnField.application_args: [
                        Bytes(SC_contract.get_method_by_name("create_app").get_selector()),
                        Txn.sender(),
                        hash.get(),
                        Itob(App.globalGet(MC_commitment_limit_key)),
                        Itob(App.globalGet(MC_frozen_duration_key)),
                    ],
                    TxnField.approval_program: Bytes("base64", SC_approval_program),
                    TxnField.clear_state_program: Bytes("base64", SC_clear_state_program),
                    TxnField.global_num_uints: Int(SC_NUM_GLOBAL_UINT),
                    TxnField.global_num_byte_slices: Int(SC_NUM_GLOBAL_BYTES),
                    TxnField.local_num_uints: Int(SC_NUM_LOCAL_UINT),
                    TxnField.local_num_byte_slices: Int(SC_NUM_LOCAL_BYTES),
                    TxnField.fee: Int(0),
                    TxnField.applications: [Global.current_application_id()],
                }
            ),
            InnerTxnBuilder.Submit(),
            # Output the App ID of the created proposal
            output.set(InnerTxn.created_application_id()),

            # Opt-in to the newly created proposal
            App.globalPut(MC_allow_optin_to_P_key, Int(OPTIN_ALLOWED)),
            InnerTxnBuilder.Begin(),
            InnerTxnBuilder.SetFields(
                {
                    TxnField.type_enum: TxnType.ApplicationCall,
                    TxnField.application_id: InnerTxn.created_application_id(),
                    TxnField.on_completion: OnComplete.OptIn,
                    TxnField.fee: Int(0),
                    TxnField.applications: [Global.current_application_id()],
                }
            ),
            InnerTxnBuilder.Submit(),
            App.globalPut(MC_allow_optin_to_P_key, Int(OPTIN_NOT_ALLOWED)),
        )


    @router.method(no_op=CallConfig.CALL)
    def proposal_update(newHash: abi.StaticBytes[Literal[32]]):

        return Seq(
            # Assert correct length of ABI compound type for hash of proposal
            Assert(Len(newHash.get()) == Int(32)),
            # Call the proposal_update method of StakingContract that is passed in Txn.applications[1]
            InnerTxnBuilder.ExecuteMethodCall(
                app_id=Txn.applications[1],
                method_signature=SC_contract.get_method_by_name("proposal_update").get_signature(),
                args=[
                    Txn.sender(),
                    newHash.get(),
                ],
                extra_fields={
                    TxnField.fee: Int(0)
                }
            ),
            # Approve the call
            Approve(),
        )

    @router.method(no_op=CallConfig.CALL)
    def ratify(outcome: abi.Uint64):
        # Get creator address of the proposal that should be ratified
        sc_id = Txn.applications[1]
        manager_app_address = AppParam.creator(sc_id)
        # Get info whether the proposal is finished already or not
        sc_finished = App.globalGetEx(sc_id, SC_finished_key)
        # Get the number of accounts still supporting the proposal
        sc_num_supporters = App.globalGetEx(sc_id, SC_num_supporters_key)
        # Get the last round the proposal has been updated
        sc_last_round = App.globalGetEx(sc_id, SC_last_round_key)

        # Escrow contract to be released from the proposal
        ec_id = Txn.applications[2]
        # Get the owner of the escrow contract
        escrow_owner = App.globalGetEx(ec_id, EC_owner_key)
        # Get the contribution reward for the escrow account
        ec_cr = App.globalGetEx(ec_id, EC_contribution_reward_key)

        # Variable for holding the reward amount
        reward_amount = ScratchVar(TealType.uint64)

        return Seq(
            manager_app_address,
            escrow_owner,
            Assert(escrow_owner.hasValue()),
            ec_cr,
            Assert(ec_cr.hasValue()),
            sc_finished,
            Assert(sc_finished.hasValue()),
            sc_num_supporters,
            Assert(sc_num_supporters.hasValue()),
            sc_last_round,
            Assert(sc_last_round.hasValue()),
            # Check if application to be removed support was also created by this app
            Assert(manager_app_address.hasValue()),
            Assert(manager_app_address.value() == Global.current_application_address()),
            # Only contract creator can ratify proposal results
            Assert(Txn.sender() == Global.creator_address()),
            # Check if proposal is finished
            If(
                sc_finished.value() == Int(FINISHED)
            ).Then(
                # Check if there are any accounts still supporting the proposal
                If(
                    sc_num_supporters.value() != Int(0)
                ).Then(
                    Seq(
                        # Release the account
                        InnerTxnBuilder.ExecuteMethodCall(
                            app_id=ec_id,
                            method_signature=EC_contract.get_method_by_name("release_ratify").get_signature(),
                            args=[
                                Itob(outcome.get())
                            ],
                            extra_fields={
                                TxnField.fee: Int(0),
                                TxnField.applications: [sc_id, Global.current_application_id()]
                            }
                        ),
                        # If the proposal passed, issue rewards to the escrow owner
                        If(
                            outcome.get() == Int(PROP_PASS)
                        ).Then(
                            Seq(
                                # Only if enough time has passed since the finish of the proposal
                                Assert(
                                    Global.round() >= Add(
                                        sc_last_round.value(),
                                        App.globalGet(MC_locking_duration_key)
                                    )
                                ),
                                # Have to assert the value after the inner Tx otherwise it is not updated!
                                ec_cr,
                                Assert(ec_cr.hasValue()),
                                # Calculate the reward amount
                                reward_amount.store(
                                    Div(
                                        Mul(
                                            ec_cr.value(),
                                            App.globalGet(MC_pass_rewards_key)
                                        ),
                                        Int(100)
                                    )
                                ),
                                # Check if escrow owner can accept the rewards, otherwise issue them to the contract
                                # creator to prevent blocking the deletion of the proposal
                                If(
                                    Balance(escrow_owner.value()) >= Global.min_balance()
                                ).Then(
                                    payTo(escrow_owner.value(), reward_amount.load())
                                )
                                .Else(
                                    payTo(Global.creator_address(), reward_amount.load())
                                ),
                                # In any case, mark in the escrow that the rewards have been paid
                                InnerTxnBuilder.ExecuteMethodCall(
                                    app_id=ec_id,
                                    method_signature=EC_contract.get_method_by_name("accept_reward").get_signature(),
                                    args=[],
                                    extra_fields={
                                        TxnField.fee: Int(0)
                                    }
                                ),
                            )
                        ),
                        Approve()
                    )
                )
                .Else(
                    Seq(
                        # There are no more accounts supporting the proposal, thus it can be deleted
                        InnerTxnBuilder.Begin(),
                        InnerTxnBuilder.SetFields(
                            {
                                TxnField.type_enum: TxnType.ApplicationCall,
                                TxnField.application_id: sc_id,
                                TxnField.on_completion: OnComplete.DeleteApplication,
                                TxnField.fee: Int(0),
                            }
                        ),
                        InnerTxnBuilder.Submit(),
                        # FOR SOME REASON THE PART BELOW GIVES A "logic eval error: app X does not exist"
                        # # The manager can clear its local state
                        # InnerTxnBuilder.Begin(),
                        # InnerTxnBuilder.SetFields(
                        #     {
                        #         TxnField.type_enum: TxnType.ApplicationCall,
                        #         TxnField.application_id: sc_id,
                        #         TxnField.on_completion: OnComplete.ClearState,
                        #         TxnField.fee: Int(0),
                        #     }
                        # ),
                        # InnerTxnBuilder.Submit(),
                        Approve()
                    )
                )
            )
            .Else(
                # Proposal isn't finished yet, thus can't be ratified
                Reject()
            ),
        )

    @router.method(no_op=CallConfig.CALL)
    def start_supporting_prop():
        # Get the proposal the user would like to start supporting
        sc_id = Txn.applications[1]
        # Get creator address of the proposal that the user would like to start supporting
        manager_app_address = AppParam.creator(sc_id)

        # Request for supporting a proposal needs to be accompanied by a funding transaction (i.e. to increase the
        # balance of the escrow account to cover the increased required minimal balance due to it opting into another
        # contract)
        prop_funding_txn_index = Txn.group_index() - Int(1)

        # Get user's escrow contract ID
        ec_id = App.localGet(Txn.sender(), MC_escrow_id_local_key)
        # Get user's escrow contract account
        ec_account = AppParam.address(ec_id)

        return Seq(
            manager_app_address,
            # Check if application to support supporting was also created by this app
            Assert(manager_app_address.hasValue()),
            Assert(manager_app_address.value() == Global.current_application_address()),
            ec_account,
            Assert(ec_account.hasValue()),
            # Assert there is funding being received by EC for supporting a proposal
            #  The transaction has to be a payment
            Assert(Gtxn[prop_funding_txn_index].type_enum() == TxnType.Payment),
            #  The transaction has to be to the user's escrow contract account
            Assert(Gtxn[prop_funding_txn_index].receiver() == ec_account.value()),
            #  The amount needs to be large enough
            Assert(Gtxn[prop_funding_txn_index].amount() >= Int(SC_FUNDING_FOR_OPTIN)),
            # Temporarily allow opting into the proposal
            App.globalPut(MC_allow_optin_to_P_key, Int(OPTIN_ALLOWED)),
            # Instruct EC to opt into the proposal
            InnerTxnBuilder.ExecuteMethodCall(
               app_id=ec_id,
               method_signature=EC_contract.get_method_by_name("start_supporting_prop").get_signature(),
               args=[],
               extra_fields={
                   TxnField.fee: Int(0),
                   TxnField.applications: [sc_id, Global.current_application_id()]
               }
            ),
            # Disable opting into proposals
            App.globalPut(MC_allow_optin_to_P_key, Int(OPTIN_NOT_ALLOWED)),
            Approve()
        )

    @router.method(no_op=CallConfig.CALL)
    def update_prop_global_state():
        # Get the proposal whose state the user would like to update
        sc_id = Txn.applications[1]
        # Get creator address of the proposal that the user would like to start supporting
        manager_app_address = AppParam.creator(sc_id)

        return Seq(
            manager_app_address,
            # Check if application to update its state was also created by this app
            Assert(manager_app_address.hasValue()),
            Assert(manager_app_address.value() == Global.current_application_address()),
            # Instruct SC to update its state
            InnerTxnBuilder.ExecuteMethodCall(
               app_id=sc_id,
               method_signature=SC_contract.get_method_by_name("update_state").get_signature(),
               args=[],
               extra_fields={
                   TxnField.fee: Int(0),
               }
            ),
            Approve()
        )

    @router.method(no_op=CallConfig.CALL)
    def remove_support_from_prop():
        # Get user's escrow contract ID
        ec_id = App.localGet(Txn.sender(), MC_escrow_id_local_key)

        # Get proposal id
        sc_id = Txn.applications[1]
        # Get creator address of the proposal from which the support should be removed
        manager_app_address = AppParam.creator(sc_id)

        # Get info whether the proposal is finished already or not
        sc_finished = App.globalGetEx(sc_id, SC_finished_key)

        return Seq(
            sc_finished,
            Assert(sc_finished.hasValue()),
            manager_app_address,
            # Check if application to be removed support was also created by this app
            Assert(manager_app_address.hasValue()),
            Assert(manager_app_address.value() == Global.current_application_address()),
            # Support can't be removed while the proposal is finished (because it's outcome and consequences haven't
            # been ratified yet)
            Assert(sc_finished.value() == Int(NOT_FINISHED)),
            # Release the escrow from supporting the proposal
            InnerTxnBuilder.ExecuteMethodCall(
                app_id=ec_id,
                method_signature=EC_contract.get_method_by_name("release_from_proposal").get_signature(),
                args=[],
                extra_fields={
                    TxnField.fee: Int(0),
                    TxnField.applications: [sc_id]
                }
            ),
            Approve()
        )

    @router.method(no_op=CallConfig.CALL)
    def add_support_to_prop(amount: abi.Uint64):
        # Get user's escrow contract ID
        ec_id = App.localGet(Txn.sender(), MC_escrow_id_local_key)

        # Get proposal id
        sc_id = Txn.applications[1]
        # Get creator address of the proposal to which support should be added
        manager_app_address = AppParam.creator(sc_id)

        return Seq(
            manager_app_address,
            # Check if application to be added support was also created by this app
            Assert(manager_app_address.hasValue()),
            Assert(manager_app_address.value() == Global.current_application_address()),
            # Call the escrow to add support to the proposal
            InnerTxnBuilder.ExecuteMethodCall(
                app_id=ec_id,
                method_signature=EC_contract.get_method_by_name("add_support").get_signature(),
                args=[
                    Itob(amount.get())
                ],
                extra_fields={
                    TxnField.fee: Int(0),
                    TxnField.applications: [sc_id]
                }
            ),
            Approve()
        )

    @router.method(no_op=CallConfig.CALL)
    def add_funds():

        ec_funding_txn_index = Txn.group_index() - Int(1)

        # Get user's escrow contract ID
        ec_id = App.localGet(Txn.sender(), MC_escrow_id_local_key)

        # Get user's escrow contract account
        ec_account = AppParam.address(ec_id)

        return Seq(
            ec_account,
            Assert(ec_account.hasValue()),
            # Assert there is funding being received by EC for supporting a proposal
            #  The transaction has to be a payment
            Assert(Gtxn[ec_funding_txn_index].type_enum() == TxnType.Payment),
            #  The transaction has to be to the user's escrow contract account
            Assert(Gtxn[ec_funding_txn_index].receiver() == ec_account.value()),

            # Call the escrow to increase the available stake by the sent amount
            InnerTxnBuilder.ExecuteMethodCall(
                app_id=ec_id,
                method_signature=EC_contract.get_method_by_name("add_funds").get_signature(),
                args=[
                    Itob(Gtxn[ec_funding_txn_index].amount())
                ],
                extra_fields={
                    TxnField.fee: Int(0),
                }
            ),
            Approve()
        )

    @router.method(no_op=CallConfig.CALL)
    def remove_funds(amount: abi.Uint64):

        # Get user's escrow contract ID
        ec_id = App.localGet(Txn.sender(), MC_escrow_id_local_key)

        # Get user's escrow contract account
        ec_account = AppParam.address(ec_id)

        return Seq(
            ec_account,
            Assert(ec_account.hasValue()),
            # Call the escrow to reduce the available stake by the requested amount
            InnerTxnBuilder.ExecuteMethodCall(
                app_id=ec_id,
                method_signature=EC_contract.get_method_by_name("remove_funds").get_signature(),
                args=[
                    Itob(amount.get())
                ],
                extra_fields={
                    TxnField.fee: Int(0),
                    TxnField.accounts: [Txn.sender()]   # sender is always the owner of escrow at this stage
                }
            ),
            Approve()
        )

    @router.method(no_op=CallConfig.CALL)
    def send_note(rcv: abi.Address, msg: abi.DynamicBytes):

        # Get user's escrow contract ID
        ec_id = App.localGet(Txn.sender(), MC_escrow_id_local_key)

        # Get user's escrow contract account
        ec_account = AppParam.address(ec_id)

        return Seq(
            ec_account,
            Assert(ec_account.hasValue()),
            # Assert correct length of ABI address
            Assert(Len(rcv.get()) == Int(32)),
            # Assert max length of message
            Assert(Len(msg.get()) <= Int(1000)),
            # Call the escrow to send a note msg to rcv
            InnerTxnBuilder.ExecuteMethodCall(
                app_id=ec_id,
                method_signature=EC_contract.get_method_by_name("send_note").get_signature(),
                args=[
                    rcv.get(),
                    msg.get()
                ],
                extra_fields={
                    TxnField.fee: Int(0),
                    TxnField.accounts: [rcv.get()]
                }
            ),
            Approve()
        )

    @router.method(no_op=CallConfig.CALL)
    def bring_online(votekey: abi.StaticBytes[Literal[32]], selkey: abi.StaticBytes[Literal[32]],
                     sprfkey: abi.StaticBytes[Literal[64]],
                     votefst: abi.Uint64, votelst: abi.Uint64, votekd: abi.Uint64):

        # Get user's escrow contract ID
        ec_id = App.localGet(Txn.sender(), MC_escrow_id_local_key)

        # Get user's escrow contract account
        ec_account = AppParam.address(ec_id)

        return Seq(
            ec_account,
            Assert(ec_account.hasValue()),
            # Assert correct lengths
            Assert(Len(votekey.get()) == Int(32)),
            Assert(Len(selkey.get()) == Int(32)),
            Assert(Len(sprfkey.get()) == Int(64)),
            # Call the escrow to send a KeyReg tx for online
            InnerTxnBuilder.ExecuteMethodCall(
                app_id=ec_id,
                method_signature=EC_contract.get_method_by_name("bring_online").get_signature(),
                args=[
                    votekey.get(),
                    selkey.get(),
                    sprfkey.get(),
                    Itob(votefst.get()),
                    Itob(votelst.get()),
                    Itob(votekd.get()),
                ],
                extra_fields={
                    TxnField.fee: Int(0),
                }
            ),
            Approve()
        )

    @router.method(no_op=CallConfig.CALL)
    def bring_offline():
        # Get user's escrow contract ID
        ec_id = App.localGet(Txn.sender(), MC_escrow_id_local_key)

        # Get user's escrow contract account
        ec_account = AppParam.address(ec_id)

        return Seq(
            ec_account,
            Assert(ec_account.hasValue()),
            # Call the escrow to send a KeyReg tx for offline
            InnerTxnBuilder.ExecuteMethodCall(
                app_id=ec_id,
                method_signature=EC_contract.get_method_by_name("bring_offline").get_signature(),
                args=[],
                extra_fields={
                    TxnField.fee: Int(0),
                }
            ),
            Approve()
        )

    return router

def compileManagerContract(algod_client):
    # Compile the program
    approval_program, clear_program, contract = getRouter().compile_program(version=7)

    with open("./compiled_files/ManagerContract_approval.teal", "w") as f:
        f.write(approval_program)

    with open("./compiled_files/ManagerContract_clear.teal", "w") as f:
        f.write(clear_program)

    with open("./compiled_files/ManagerContract.json", "w") as f:
        import json

        f.write(json.dumps(contract.dictify()))

    # Compile program to binary
    approval_program_compiled = compile_program(algod_client, approval_program)
    # Compile program to binary
    clear_state_program_compiled = compile_program(algod_client, clear_program)

    approval_program_compiled_b64 = compile_program_b64(algod_client, approval_program)
    ExtraProgramPages = math.ceil(len(base64.b64decode(approval_program_compiled_b64)) / 2048) - 1 + 1

    return [approval_program_compiled, clear_state_program_compiled,
            ExtraProgramPages, contract]
