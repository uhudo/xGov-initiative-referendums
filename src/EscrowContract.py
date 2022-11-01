from pyteal import *
import math
import base64
from typing import Literal
from util import *
from algosdk.v2client import algod
from src.config import *


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

# -----     On delete     -----
on_delete = Seq(
    # Only the contract creator can delete the contract
    Assert(Txn.sender() == Global.creator_address()),
    # Close the contract account to the escrow owner
    closeAccountTo(App.globalGet(EC_owner_key)),
    Approve(),
)

# -----       Router      -----

def getRouter():

    # Main router class
    router = Router(
        # Name of the contract
        "EscrowContract",
        # What to do for each on-complete type when no arguments are passed (bare call)
        BareCallActions(
            # Updating the contract is not allowed
            update_application=OnCompleteAction.always(Reject()),
            # Deleting the contract is allowed in certain cases
            delete_application=OnCompleteAction.call_only(on_delete),
            # There is no local state used, thus it's not necessary to handle it
            opt_in=OnCompleteAction.never(),
            close_out=OnCompleteAction.never(),
            clear_state=OnCompleteAction.never(),
        ),
    )


    @router.method(no_op=CallConfig.CREATE)
    def create_app(owner: abi.Address):

        return Seq(
            # Assert correct length of ABI address
            Assert(Len(owner.get()) == Int(32)),
            # Set global variables
            App.globalPut(EC_owner_key, owner.get()),
            # Initialize remaining global variables
            App.globalPut(EC_available_stake_key, Int(0)),
            App.globalPut(EC_contribution_reward_key, Int(0)),
            App.globalPut(EC_num_support_props_key, Int(0)),
            Approve()
        )


    @router.method(no_op=CallConfig.CALL)
    def start_supporting_prop():
        # Get creator address of the application to be opted into
        sc_id = Txn.applications[1]
        manager_app_address = AppParam.creator(sc_id)
        # Get the ID of the manager contract
        ma_id = Txn.applications[2]

        return Seq(
            manager_app_address,
            # Assert sender is contract creator - the only account that can make changes
            Assert(Txn.sender() == Global.creator_address()),
            # Increase number of proposals this escrow is supporting
            App.globalPut(
                EC_num_support_props_key,
                Add(
                    App.globalGet(EC_num_support_props_key),
                    Int(1)
                )
            ),
            # Check if application to be opted into was also created by the same account as this app
            Assert(manager_app_address.hasValue()),
            Assert(manager_app_address.value() == Global.creator_address()),
            # Opt-in to the proposal contract - will fail if not allowed by proposal creator contract (i.e. manager)
            InnerTxnBuilder.Begin(),
            InnerTxnBuilder.SetFields(
                {
                    TxnField.type_enum: TxnType.ApplicationCall,
                    TxnField.application_id: sc_id,
                    TxnField.on_completion: OnComplete.OptIn,
                    TxnField.fee: Int(0),
                    TxnField.applications: [ma_id],
                }
            ),
            InnerTxnBuilder.Submit(),
            Approve(),
        )

    @router.method(no_op=CallConfig.CALL)
    def add_support(amount: abi.Uint64):
        # Get creator address of the application to which the support should be added
        sc_id = Txn.applications[1]
        manager_app_address = AppParam.creator(sc_id)

        return Seq(
            manager_app_address,
            # Assert sender is contract creator - the only account that can make changes
            Assert(Txn.sender() == Global.creator_address()),
            # Check if application to be add support was also created by the same account as this app
            Assert(manager_app_address.hasValue()),
            Assert(manager_app_address.value() == Global.creator_address()),
            # Support to a proposal can only be added if there is enough of available stake in the escrow
            If(
                amount.get() <= App.globalGet(EC_available_stake_key)
            ).Then(
                Seq(
                    # Available stake is reduced by the amount given to the proposal
                    App.globalPut(
                        EC_available_stake_key,
                        Minus(
                            App.globalGet(EC_available_stake_key),
                            amount.get()
                        )
                    ),
                    # Notify the proposal of the increased support
                    InnerTxnBuilder.ExecuteMethodCall(
                        app_id=sc_id,
                        method_signature=SC_contract.get_method_by_name("add_stake").get_signature(),
                        args=[
                            Itob(amount.get())
                        ],
                        extra_fields={
                            TxnField.fee: Int(0)
                        }
                    ),
                    Approve(),
                )
            )
            .Else(
                Reject()
            ),
        )

    @router.method(no_op=CallConfig.CALL)
    def add_funds(amount: abi.Uint64):
        return Seq(
            # Assert sender is contract creator - the only account that can make changes
            Assert(Txn.sender() == Global.creator_address()),
            # Increase the available stake by the approved amount
            App.globalPut(
                EC_available_stake_key,
                Add(
                    App.globalGet(EC_available_stake_key),
                    amount.get()
                )
            ),
            Approve(),
        )

    @router.method(no_op=CallConfig.CALL)
    def remove_funds(amount: abi.Uint64):
        return Seq(
            # Assert sender is contract creator - the only account that can make changes
            Assert(Txn.sender() == Global.creator_address()),
            # Funds can be removed only if there is any available stake
            If(
                App.globalGet(EC_available_stake_key) >= amount.get()
            ).Then(
                Seq(
                    # Reduce the available stake by the approved amount
                    App.globalPut(
                        EC_available_stake_key,
                        Minus(
                            App.globalGet(EC_available_stake_key),
                            amount.get()
                        )
                    ),
                    # Send the amount to the escrow owner
                    payTo(App.globalGet(EC_owner_key), amount.get()),
                    Approve(),
                )
            )
            .Else(
                Reject()
            )
        )

    @router.method(no_op=CallConfig.CALL)
    def accept_reward():
        return Seq(
            # Assert sender is contract creator - the only account that can make changes
            Assert(Txn.sender() == Global.creator_address()),
            # Reset contribution reward amount
            App.globalPut(EC_contribution_reward_key, Int(0))
        )

    @router.method(no_op=CallConfig.CALL)
    def release_ratify(outcome: abi.Uint64):
        #  Depending on the outcome, the escrow is differently released from proposal Txn.applications[1]
        #  In all cases, the available_stake is increased by the amount the account attributed to the proposal, and the
        #  number of proposals it supports is decreased.
        #  The escrow outs out of the proposal contract.
        #  If PROP_PASS: contribution_reward is set according to the time-weighted stake escrow contributed to the
        #  proposal.
        #  If PROP_CLAWBACK: Percentage of stake that supported a proposal that was vetoed is sent to the contract
        #  creator, i.e. the manager, and the available stake reduced by that amount.
        #  If PROP_REJECT: Nothing additionally happens.

        # Get creator address of the application from which the escrow should be released
        sc_id = Txn.applications[1]
        manager_app_address = AppParam.creator(sc_id)

        # Get the stake the escrow has supporting the proposal
        sc_local_stake = App.localGetEx(Global.current_application_address(), sc_id, SC_stake_local_key)
        # Get the last round the escrow's status of the proposal has been updated
        sc_local_last_round = App.localGetEx(Global.current_application_address(), sc_id, SC_last_round_local_key)
        # Get the time-weighted stake the escrow has supported the proposal with
        sc_local_weighted_stake = App.localGetEx(Global.current_application_address(), sc_id, SC_weighted_stake_local_key)

        # Get the last round the proposal has been updated
        sc_last_round = App.globalGetEx(sc_id, SC_last_round_key)
        # Get the total time-weighted stake of the proposal
        sc_weighted_stake = App.globalGetEx(sc_id, SC_weighted_stake_key)

        # Get the clawback percentage from the manager contract
        ma_id = Txn.applications[2]
        ma_clp = App.globalGetEx(ma_id, MC_clawback_percentage_key)

        # Variable for holding the amount to be clawed back
        clawback_amount = ScratchVar(TealType.uint64)

        return Seq(
            manager_app_address,
            ma_clp,
            Assert(ma_clp.hasValue()),
            sc_local_stake,
            Assert(sc_local_stake.hasValue()),
            sc_local_last_round,
            Assert(sc_local_last_round.hasValue()),
            sc_local_weighted_stake,
            Assert(sc_local_weighted_stake.hasValue()),
            sc_last_round,
            Assert(sc_last_round.hasValue()),
            sc_weighted_stake,
            Assert(sc_weighted_stake.hasValue()),

            # Assert sender is contract creator - the only account that can make changes
            Assert(Txn.sender() == Global.creator_address()),
            # Check if application from which escrow should be released was created by the same account as this app
            Assert(manager_app_address.hasValue()),
            Assert(manager_app_address.value() == Global.creator_address()),
            # Increase the available stake by the amount the account attributed to the proposal
            App.globalPut(
                EC_available_stake_key,
                Add(
                    App.globalGet(EC_available_stake_key),
                    sc_local_stake.value()
                )
            ),
            # Decrease the number of proposals the escrow is supporting
            App.globalPut(
                EC_num_support_props_key,
                Minus(
                    App.globalGet(EC_num_support_props_key),
                    Int(1)
                )
            ),
            # Calculate amount that can be clawed back if the proposal was vetoed
            clawback_amount.store(
                Div(
                    Mul(
                        sc_local_stake.value(),
                        ma_clp.value()
                    ),
                    Int(100)
                )
            ),
            # Check what was the outcome of the proposal
            If(
                outcome.get() == Int(PROP_PASS)
            ).Then(
                # If outcome is the proposal won, contribution_reward is set according to the time-weighted stake escrow
                # contributed to the proposal, i.e.:
                #  CR[%] = (((global_LR - local_LR) * local_S + local_WS) * 100) / global_WS
                App.globalPut(
                    EC_contribution_reward_key,
                    Div(
                        Mul(
                            Add(
                                Mul(
                                    Minus(
                                        sc_last_round.value(),
                                        sc_local_last_round.value()
                                    ),
                                    sc_local_stake.value()
                                ),
                                sc_local_weighted_stake.value()
                            ),
                            Int(100)
                        ),
                        sc_weighted_stake.value()
                    )
                )
            )
            .Else(
                If(
                    outcome.get() == Int(PROP_CLAWBACK)
                ).Then(
                    # If outcome is the proposal was vetoed, a percentage of the contributing support is clawed back
                    payTo(
                        Global.creator_address(),
                        clawback_amount.load()
                    )
                )
                # If outcome is reject, nothing special needs to be done
            ),
            # Opt out of the proposal contract
            InnerTxnBuilder.Begin(),
            InnerTxnBuilder.SetFields(
                {
                    TxnField.type_enum: TxnType.ApplicationCall,
                    TxnField.application_id: sc_id,
                    TxnField.on_completion: OnComplete.CloseOut,
                    TxnField.fee: Int(0),
                    # TxnField.applications: [ma_id], # not needed
                }
            ),
            InnerTxnBuilder.Submit(),
            # The available stake is increased by the opt-in stake required for connecting to the proposal contract
            App.globalPut(
                EC_available_stake_key,
                Add(
                    App.globalGet(EC_available_stake_key),
                    Int(SC_FUNDING_FOR_OPTIN)
                )
            ),
            # In case of clawback, the available stake is reduced by the clawed amount
            If(
                outcome.get() == Int(PROP_CLAWBACK)
            ).Then(
                App.globalPut(
                    EC_available_stake_key,
                    Minus(
                        App.globalGet(EC_available_stake_key),
                        clawback_amount.load()
                    )
                )
            ),
            Approve(),
        )

    @router.method(no_op=CallConfig.CALL)
    def release_from_proposal():
        #  Depending on whether the SC is finished, the EC can close out or not

        # Get creator address of the application from which the escrow should be released
        sc_id = Txn.applications[1]
        manager_app_address = AppParam.creator(sc_id)

        # Get the stake the escrow has supporting the proposal
        sc_local_stake = App.localGetEx(Global.current_application_address(), sc_id, SC_stake_local_key)

        # Get info about whether the SC is finished or not
        sc_finished = App.globalGetEx(sc_id, SC_finished_key)

        # Variable for holding the amount to be clawed back
        tmp_sc_local_stake = ScratchVar(TealType.uint64)

        return Seq(
            manager_app_address,
            sc_local_stake,
            Assert(sc_local_stake.hasValue()),
            sc_finished,
            Assert(sc_finished.hasValue()),

            # Assert sender is contract creator - the only account that can make changes
            Assert(Txn.sender() == Global.creator_address()),
            # Check if application from which escrow should be released was created by the same account as this app
            Assert(manager_app_address.hasValue()),
            Assert(manager_app_address.value() == Global.creator_address()),

            # Store the amount the account attributed to the proposal
            tmp_sc_local_stake.store(
                sc_local_stake.value()
            ),

            # Opt out of the proposal contract
            InnerTxnBuilder.Begin(),
            InnerTxnBuilder.SetFields(
                {
                    TxnField.type_enum: TxnType.ApplicationCall,
                    TxnField.application_id: sc_id,
                    TxnField.on_completion: OnComplete.CloseOut,
                    TxnField.fee: Int(0),
                }
            ),
            InnerTxnBuilder.Submit(),

            # Check what is the status of the proposal after the opt-out
            If(
                sc_finished.value() == Int(NOT_FINISHED)
            ).Then(
                # If proposal is not finished, then the stake can really be removed from the proposal
                Seq(
                    # Increase the available stake by the amount the account attributed to the proposal plus
                    # the costs of opt-in to the contract
                    App.globalPut(
                        EC_available_stake_key,
                        Add(
                            App.globalGet(EC_available_stake_key),
                            tmp_sc_local_stake.load(),
                            Int(SC_FUNDING_FOR_OPTIN)
                        )
                    ),
                    # Decrease the number of proposals the escrow is supporting
                    App.globalPut(
                        EC_num_support_props_key,
                        Minus(
                            App.globalGet(EC_num_support_props_key),
                            Int(1)
                        )
                    ),
                    Approve()
                )
            )
            .Else(
                # Proposal is finished, thus the stake cannot be removed - must go through ratification process
                Reject()
            ),
        )

    @router.method(no_op=CallConfig.CALL)
    def send_note(rcv: abi.Address, msg: abi.DynamicBytes):
        return Seq(
            # Assert correct length of ABI address
            Assert(Len(rcv.get()) == Int(32)),
            # Assert max length of message
            Assert(Len(msg.get()) <= Int(1000)),
            # Assert sender is contract creator - the only account that can make changes
            Assert(Txn.sender() == Global.creator_address()),
            # Issue a 0 payment transaction to rcv with note msg
            InnerTxnBuilder.Begin(),
            InnerTxnBuilder.SetFields(
                {
                    TxnField.type_enum: TxnType.Payment,
                    TxnField.receiver: rcv.get(),
                    TxnField.amount: Int(0),
                    TxnField.fee: Int(0),
                    TxnField.note: msg.get(),
                }
            ),
            InnerTxnBuilder.Submit(),
            Approve()
        )

    @router.method(no_op=CallConfig.CALL)
    def bring_online(votekey: abi.StaticBytes[Literal[32]], selkey: abi.StaticBytes[Literal[32]],
                     sprfkey: abi.StaticBytes[Literal[64]],
                     votefst: abi.Uint64, votelst: abi.Uint64, votekd: abi.Uint64):
        return Seq(
            # Assert correct lengths
            Assert(Len(votekey.get()) == Int(32)),
            Assert(Len(selkey.get()) == Int(32)),
            Assert(Len(sprfkey.get()) == Int(64)),
            # Assert sender is contract creator - the only account that can make changes
            Assert(Txn.sender() == Global.creator_address()),
            # Issue a KeyReg transaction for online
            InnerTxnBuilder.Begin(),
            InnerTxnBuilder.SetFields(
                {
                    TxnField.type_enum: TxnType.KeyRegistration,
                    TxnField.vote_pk: votekey.get(),
                    TxnField.selection_pk: selkey.get(),
                    TxnField.state_proof_pk: sprfkey.get(),
                    TxnField.vote_first: votefst.get(),
                    TxnField.vote_last: votelst.get(),
                    TxnField.vote_key_dilution: votekd.get(),
                    TxnField.fee: Int(0),
                }
            ),
            InnerTxnBuilder.Submit(),
            Approve()
        )

    @router.method(no_op=CallConfig.CALL)
    def bring_offline():
        return Seq(
            # Assert sender is contract creator - the only account that can make changes
            Assert(Txn.sender() == Global.creator_address()),
            # Issue a KeyReg transaction for offline
            InnerTxnBuilder.Begin(),
            InnerTxnBuilder.SetFields(
                {
                    TxnField.type_enum: TxnType.KeyRegistration,
                    TxnField.fee: Int(0),
                }
            ),
            InnerTxnBuilder.Submit(),
            Approve()
        )

    return router


def compileEscrowContract(algod_client):
    # Compile the program
    approval_program, clear_program, contract = getRouter().compile_program(version=7)

    with open("./compiled_files/EscrowContract_approval.teal", "w") as f:
        f.write(approval_program)

    with open("./compiled_files/EscrowContract_clear.teal", "w") as f:
        f.write(clear_program)

    with open("./compiled_files/EscrowContract.json", "w") as f:
        import json

        f.write(json.dumps(contract.dictify()))

    # Compile program to bytes
    approval_program_compiled_b64 = compile_program_b64(algod_client, approval_program)
    ExtraProgramPages = math.ceil(len(base64.b64decode(approval_program_compiled_b64)) / 2048) - 1
    # Compile program to bytes
    clear_state_program_compiled_b64 = compile_program_b64(algod_client, clear_program)


    # Required funding for the creation of the escrow [microAlgo]
    FUNDING_FOR_CREATION = 100_000*(1+ExtraProgramPages) + \
                           (25_000+3_500)*EC_NUM_GLOBAL_UINT + \
                           (25_000+25_000)*EC_NUM_GLOBAL_BYTES + \
                           100_000

    return [approval_program_compiled_b64, clear_state_program_compiled_b64,
            FUNDING_FOR_CREATION, ExtraProgramPages, contract]
