from pyteal import *
# ----- ----- -----    Constants     ----- ----- -----

# ----- -----    General     ----- -----
# Unique encoding defining different possible outcomes of proposals
PROP_REJECT = 0
PROP_PASS = 1
PROP_CLAWBACK = 2

OPTIN_NOT_ALLOWED = 0
OPTIN_ALLOWED = 1

NOT_FINISHED = 0
FINISHED = 1

NOT_FROZEN = 0
FROZEN = 1

# ----- -----    Manager Contract     ----- -----

# ----- Global variables  -----
# Number of global variables
MC_NUM_GLOBAL_UINT = 6
MC_NUM_GLOBAL_BYTES = 0

# Allow opting into proposal P
MC_allow_optin_to_P_key = Bytes("AOITP")

# Commitment Limit: time-weighted stake a proposal needs to gather before it is put up to a vote
MC_commitment_limit_key = Bytes("CL")

# Froze Duration: number of rounds the time-weighted stake is not updated from the time the proposer updates the
# proposal. This is to give time to supporters to decide whether they would like to continue supporting the updated
# proposal or rather remove their commitment.
MC_frozen_duration_key = Bytes("FD")

# Locking Duration: number of rounds the stake supporting a winning proposal remains hard-locked after it has reached
# the required commitment limit. This is to ensure the supporters stand behind the consequences of a passing proposal.
MC_locking_duration_key = Bytes("LD")

# Clawback Percentage: percentage of stake clawed back from a vetoed proposal (e.g. spam or malicious proposals)
MC_clawback_percentage_key = Bytes("CP")

# Pass Rewards: amount of rewards distributed pro rata amongst supporters of a passing proposal
MC_pass_rewards_key = Bytes("PR")

# -----  Local variables  -----

# Number of global variables
MC_NUM_LOCAL_UINT = 1
MC_NUM_LOCAL_BYTES = 0

# ID of the escrow contract belonging to the account
MC_escrow_id_local_key = Bytes("ecid")

# ----- -----    Staking Contract     ----- -----
# ----- Global variables  -----

# Number of global variables
SC_NUM_GLOBAL_UINT = 9
SC_NUM_GLOBAL_BYTES = 2

# Weighted Stake: total time-weighted stake committed so far
SC_weighted_stake_key = Bytes("WS")
# Stake: total stake committed so far
SC_stake_key = Bytes("S")
# Last Round: Number of the last round the time-weighted stake has been evaluated
SC_last_round_key = Bytes("LR")

# Proposer: address of the proposer
SC_proposer_key = Bytes("P")
# Proposal hash: Hash of the proposal
SC_proposal_hash_key = Bytes("H")

# Commitment Limit: time-weighted stake a proposal needs to gather before it is put up to a vote
SC_commitment_limit_key = Bytes("CL")
# Froze Duration: number of rounds the time-weighted stake is not updated from the time the proposer updates the
# proposal. This is to give time to supporters to decide whether they would like to continue supporting the updated
# proposal or rather remove their commitment.
SC_frozen_duration_key = Bytes("FD")
# Finished: set when the proposal has reached the commitment limit. Changes to the proposal or stake not possible
# anymore.
SC_finished_key = Bytes("FI")
# Frozen: set when the proposal has been updated and is waiting for the frozen duration to pass.
SC_frozen_key = Bytes("FR")

# Number of accounts supporting the proposal
SC_num_supporters_key = Bytes("NS")

# App ID of the manager contract that controls the opt-in
SC_manager_app_key = Bytes("MAID")

# -----  Local variables  -----

# Number of global variables
SC_NUM_LOCAL_UINT = 3
SC_NUM_LOCAL_BYTES = 0

# Weighted Stake: time-weighted stake committed so far by a supporter
SC_weighted_stake_local_key = Bytes("WS")
# Stake: total stake committed so far by a supporter
SC_stake_local_key = Bytes("S")
# Last Round: Number of the last round the time-weighted stake of a supporter has been evaluated
SC_last_round_local_key = Bytes("LR")


# ----- -----    Escrow Contract     ----- -----
# ----- Global variables  -----

# Number of global variables
EC_NUM_GLOBAL_UINT = 3
EC_NUM_GLOBAL_BYTES = 1

# Owner: address of owner of funds in the escrow
EC_owner_key = Bytes("Owner")

# Available stake that can be used to support proposals
EC_available_stake_key = Bytes("AS")

# Percentage reward for supporting a proposal that passed
EC_contribution_reward_key = Bytes("CR")

# Number of proposals the escrow is supporting
EC_num_support_props_key = Bytes("NSP")


# -----  Local variables  -----

# Number of global variables
EC_NUM_LOCAL_UINT = 0
EC_NUM_LOCAL_BYTES = 0

# ----- ----- -----                ----- ----- -----

SC_approval_program = None
SC_clear_state_program = None
SC_FUNDING_FOR_CREATION = None
SC_FUNDING_FOR_OPTIN = None
SC_contract = None

EC_approval_program = None
EC_clear_state_program = None
EC_FUNDING_FOR_CREATION = None
EC_ExtraProgramPages = None
EC_contract = None

MC_approval_program = None
MC_clear_state_program = None
MC_ExtraProgramPages = None
MC_contract = None

def init_global_vars(algod_client):
    # Get info about StakingContract
    import src.StakingContract as SC
    global SC_approval_program, SC_clear_state_program, SC_FUNDING_FOR_CREATION, SC_FUNDING_FOR_OPTIN, SC_contract
    [SC_approval_program, SC_clear_state_program, SC_FUNDING_FOR_CREATION, SC_FUNDING_FOR_OPTIN, SC_contract] = \
        SC.compileStakingContract(algod_client)

    # Get info about EscrowContract
    import src.EscrowContract as EC
    global EC_approval_program, EC_clear_state_program, EC_FUNDING_FOR_CREATION, EC_ExtraProgramPages, EC_contract
    [EC_approval_program, EC_clear_state_program, EC_FUNDING_FOR_CREATION, EC_ExtraProgramPages, EC_contract] = \
        EC.compileEscrowContract(algod_client)

    # Get info about ManagerContract
    import src.ManagerContract as MC
    global MC_approval_program, MC_clear_state_program, MC_ExtraProgramPages, MC_contract
    [MC_approval_program, MC_clear_state_program, MC_ExtraProgramPages, MC_contract] = \
        MC.compileManagerContract(algod_client)