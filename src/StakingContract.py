import base64
import math
from pyteal import *
from typing import Literal
from util import *
from algosdk.v2client import algod
from src.config import *


# -----    Subroutines    -----

# finished():
#  Returns FINISHED if commitment limit `CL` has been reached, and NOT_FINISHED otherwise.
#  It also updates the weighted-stake `WS` and the round of the last update `LR` for the contract and the contribution
#  of the account that called the method (i.e. the local `WS` and `LR`).
#  If the update results in reaching the commitment limit `CL`, the method sets the global status finished `FI`.
#  The update is only executed if the staking is not frozen, i.e. `FR` is cleared.
#  If the staking is frozen, it is checked if the freeze duration `FR` from the time the staking has been frozen has
#  already passed. In this case, the staking is unfrozen, i.e. `FR` is set, and the state of `WS` and `LR` updated
#  (both global and local).
#
@Subroutine(TealType.uint64)
def finished() -> Expr:
    update_state = Seq(
        # Update global time-weighted stake as:
        #  WS = WS + (currentRound - LR)*S
        App.globalPut(
            SC_weighted_stake_key,
            Add(
                App.globalGet(SC_weighted_stake_key),
                Mul(
                    Minus(
                        Global.round(),
                        App.globalGet(SC_last_round_key)
                    ),
                    App.globalGet(SC_stake_key)
                )
            )
        ),
        # Update global last round number
        App.globalPut(SC_last_round_key, Global.round()),
        # Update local time-weighted stake as:
        #  local_WS = local_WS + (currentRound - local_LR)*local_S
        App.localPut(
            Txn.sender(),
            SC_weighted_stake_local_key,
            Add(
                App.localGet(Txn.sender(), SC_weighted_stake_local_key),
                Mul(
                    Minus(
                        Global.round(),
                        App.localGet(Txn.sender(), SC_last_round_local_key)
                    ),
                    App.localGet(Txn.sender(), SC_stake_local_key)
                )
            )
        ),
        # Update local last round number
        App.localPut(Txn.sender(), SC_last_round_local_key, Global.round()),
        # Check if with updated state the commitment limit has been reached
        If(
            App.globalGet(SC_weighted_stake_key) >= App.globalGet(SC_commitment_limit_key)
        ).Then(
            # Commitment limit has been reached
            Seq(
                # Mark that proposal is finished
                App.globalPut(SC_finished_key, Int(FINISHED)),
                Int(FINISHED)
            )
        )
        .Else(
            Int(NOT_FINISHED)
        )
    )

    return(
        # Check if proposal is finished
        If(
            App.globalGet(SC_finished_key) == Int(FINISHED)
        ).Then(
            Int(FINISHED)
        )
        .Else(
            # Proposal is ongoing
            # Check if staking is frozen
            If(
                App.globalGet(SC_frozen_key) == Int(FROZEN)
            ).Then(
                # Staking is frozen
                Seq(
                    # Bring local state up to date, i.e. to freezing time
                    #  local_WS = local_WS + (global_LR - local_LR)*local_S
                    App.localPut(
                        Txn.sender(),
                        SC_weighted_stake_local_key,
                        Add(
                            App.localGet(Txn.sender(), SC_weighted_stake_local_key),
                            Mul(
                                Minus(
                                    App.globalGet(SC_last_round_key),
                                    App.localGet(Txn.sender(), SC_last_round_local_key)
                                ),
                                App.localGet(Txn.sender(), SC_stake_local_key)
                            )
                        )
                    ),
                    #  local_LR = global_LR
                    App.localPut(
                        Txn.sender(),
                        SC_last_round_local_key,
                        App.globalGet(SC_last_round_key)
                    ),
                    # Check if freezing duration has already passed
                    If(
                        Global.round() >= App.globalGet(SC_last_round_key) + App.globalGet(SC_frozen_duration_key)
                    ).Then(
                        Seq(
                            # Unfreeze the staking
                            App.globalPut(SC_frozen_key, Int(NOT_FROZEN)),
                            # Update the state
                            update_state
                        )
                    )
                    .Else(
                        Int(NOT_FINISHED)
                    )
                )
            )
            .Else(
                # Staking is not frozen, thus the state can be updated
                update_state
            )
        )
    )

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
    Assert(
        And(
            # Only the contract creator can delete the contract
            Txn.sender() == Global.creator_address(),
            # The contract can only be deleted if the proposal has finished
            App.globalGet(SC_finished_key) == Int(FINISHED),
            # The contract can only be deleted if all accounts have been closed out
            App.globalGet(SC_num_supporters_key) == Int(0),
        ),
    ),
    # Close the contract account to the contract creator
    closeAccountTo(Global.creator_address()),
    Approve(),
)

# -----   On close out    -----
on_close_out = Seq(
    # Check if proposal is finished
    If(
        finished() == Int(NOT_FINISHED)
    ).Then(
        # The proposal is not yet finished.
        Seq(
            # Remove the support of the proposal by this supporter as:
            #  global_WS = global_WS - local_WS
            App.globalPut(
                SC_weighted_stake_key,
                Minus(
                    App.globalGet(SC_weighted_stake_key),
                    App.localGet(Txn.sender(), SC_weighted_stake_local_key)
                )
            ),
            #  global_S = global_S - local_S
            App.globalPut(
                SC_stake_key,
                Minus(
                    App.globalGet(SC_stake_key),
                    App.localGet(Txn.sender(), SC_stake_local_key)
                )
            )
        )
    ),
    # Reduce number of supporters for 1: NS = NS - 1
    App.globalPut(
        SC_num_supporters_key,
        Minus(
            App.globalGet(SC_num_supporters_key),
            Int(1)
        )
    ),
    Approve(),
)


# -----    On opt in      -----
# Get whether opt-in is allowed by manager contract
optin_allowed = App.globalGetEx(App.globalGet(SC_manager_app_key), MC_allow_optin_to_P_key)

on_opt_in = Seq(
    optin_allowed,
    # Opt-in can only be done if the proposal is not yet finished
    Assert(finished() == Int(NOT_FINISHED)),
    # Opt-in can be done only if allowed by manager contract
    Assert(optin_allowed.hasValue()),
    Assert(optin_allowed.value() == Int(OPTIN_ALLOWED)),
    # Initialize the local variables
    App.localPut(Txn.sender(), SC_weighted_stake_local_key, Int(0)),
    App.localPut(Txn.sender(), SC_stake_local_key, Int(0)),
    App.localPut(Txn.sender(), SC_last_round_local_key, App.globalGet(SC_last_round_key)),
    # If the opt-in account is not the contract creator, increase the number of supporters
    If(
        Txn.sender() != Global.creator_address()
    ).Then(
        # Increase number of supporters
        App.globalPut(
            SC_num_supporters_key,
            Add(
                App.globalGet(SC_num_supporters_key),
                Int(1)
            )
        )
    )
)

# -----       Router      -----

def getRouter():
    # Main router class
    router = Router(
        # Name of the contract
        "StakingContract",
        # What to do for each on-complete type when no arguments are passed (bare call)
        BareCallActions(
            # Updating the contract is not allowed
            update_application=OnCompleteAction.always(Reject()),
            # Deleting the contract is allowed in certain cases
            delete_application=OnCompleteAction.call_only(on_delete),
            # Closing out is allowed in certain cases
            close_out=OnCompleteAction.call_only(on_close_out),
            # Clearing the state is always allowed because only specific (i.e. controlled) accounts can opt-in
            clear_state=OnCompleteAction.call_only(Approve()),
            # Opt-in is allowed in only certain cases
            opt_in=OnCompleteAction.call_only(on_opt_in),
        ),
    )


    @router.method(no_op=CallConfig.CREATE)
    def create_app(proposer: abi.Address, propHash: abi.StaticBytes[Literal[32]], commitLimit: abi.Uint64, frozenDuration: abi.Uint64):
        # Get address of the application passed with creation of this application
        manager_app_address = AppParam.address(Txn.applications[1])

        return Seq(
            manager_app_address,
            # Assert correct length of ABI address
            Assert(Len(proposer.get()) == Int(32)),
            # Assert correct length of ABI compound type for hash of proposal
            Assert(Len(propHash.get()) == Int(32)),
            # Set global variables
            App.globalPut(SC_proposer_key, proposer.get()),
            App.globalPut(SC_proposal_hash_key, propHash.get()),
            App.globalPut(SC_commitment_limit_key, commitLimit.get()),
            App.globalPut(SC_frozen_duration_key, frozenDuration.get()),
            # Initialize remaining global variables
            App.globalPut(SC_finished_key, Int(NOT_FINISHED)),
            App.globalPut(SC_frozen_key, Int(NOT_FROZEN)),
            App.globalPut(SC_stake_key, Int(0)),
            App.globalPut(SC_weighted_stake_key, Int(0)),
            App.globalPut(SC_last_round_key, Global.round()),
            App.globalPut(SC_num_supporters_key, Int(0)),
            # Check if application passed with creation of this app is the address that issued the creation
            Assert(manager_app_address.hasValue()),
            Assert(manager_app_address.value() == Txn.sender()),
            # Store ID of the manager contract
            App.globalPut(SC_manager_app_key, Txn.applications[1]),
            Approve()
        )


    @router.method(no_op=CallConfig.CALL)
    def proposal_update(proposer: abi.Address, newHash: abi.StaticBytes[Literal[32]]):
        return Seq(
            # Assert correct length of ABI address
            Assert(Len(proposer.get()) == Int(32)),
            # Assert correct length of ABI compound type for hash of proposal
            Assert(Len(newHash.get()) == Int(32)),
            # Proposal can be updated only if it has not yet been finished
            Assert(finished() == Int(NOT_FINISHED)),
            # Proposal can be updated only if it is not frozen
            Assert(App.globalGet(SC_frozen_key) == Int(NOT_FROZEN)),
            # Proposal update can only be executed if sent by the contract creator
            Assert(Txn.sender() == Global.creator_address()),
            # Proposal can only be updated by the initial proposer
            Assert(App.globalGet(SC_proposer_key) == proposer.get()),
            # The staking is frozen
            App.globalPut(SC_frozen_key, Int(FROZEN)),
            # Store the new hash
            App.globalPut(SC_proposal_hash_key, newHash.get()),
            Approve(),
        )

    @router.method(no_op=CallConfig.CALL)
    def update_state():
        # (Try) updating the time-weighted stake
        return Pop(finished())

    @router.method(no_op=CallConfig.CALL)
    def add_stake(amount: abi.Uint64):
        return Seq(
            # Stake can only be changed if the proposal is not yet finished
            Assert(finished() == Int(NOT_FINISHED)),
            # Increase the global stake by the amount
            #  global_S = global_S + amount
            App.globalPut(
                SC_stake_key,
                Add(
                    App.globalGet(SC_stake_key),
                    amount.get()
                )
            ),
            # Increase the local stake by the amount
            #  local_S = local_S + amount
            App.localPut(
                Txn.sender(),
                SC_stake_local_key,
                Add(
                    App.localGet(Txn.sender(), SC_stake_local_key),
                    amount.get()
                )
            ),
            Approve(),
        )

    return router

def compileStakingContract(algod_client):
    # Compile the program
    approval_program, clear_program, contract = getRouter().compile_program(version=7)

    with open("./compiled_files/StakingContract_approval.teal", "w") as f:
        f.write(approval_program)

    with open("./compiled_files/StakingContract_clear.teal", "w") as f:
        f.write(clear_program)

    with open("./compiled_files/StakingContract.json", "w") as f:
        import json

        f.write(json.dumps(contract.dictify()))

    # Compile program to bytes
    approval_program_compiled_b64 = compile_program_b64(algod_client, approval_program)
    ExtraProgramPages = math.ceil(len(base64.b64decode(approval_program_compiled_b64)) / 2048) - 1
    # Compile program to bytes
    clear_state_program_compiled_b64 = compile_program_b64(algod_client, clear_program)

    # Required funding for the creation of a new proposal [microAlgo]
    FUNDING_FOR_CREATION = 100_000 * (1 + ExtraProgramPages) + \
                            (25_000 + 3_500) * SC_NUM_GLOBAL_UINT + \
                            (25_000 + 25_000) * SC_NUM_GLOBAL_BYTES

    # Required funding for opt-in to a proposal [microAlgo]
    FUNDING_FOR_OPTIN = 100_000 + \
                        (25_000 + 3_500) * SC_NUM_LOCAL_UINT + \
                        (25_000 + 25_000) * SC_NUM_LOCAL_BYTES

    return [approval_program_compiled_b64, clear_state_program_compiled_b64,
            FUNDING_FOR_CREATION, FUNDING_FOR_OPTIN, contract]
