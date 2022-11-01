# -----------------           Imports          -----------------
import base64
from hashlib import sha256
import glob
from algosdk.v2client import algod, indexer
from algosdk.future import transaction
from algosdk import account, mnemonic, error
from algosdk.abi import Contract
from algosdk import encoding
from algosdk.atomic_transaction_composer import AtomicTransactionComposer, AccountTransactionSigner, \
    TransactionWithSigner
from algosdk.logic import get_application_address
from util import *
from demo.interact_w_ManagerContract import *
import src.config as cfg

# -----------------       Global variables      -----------------
# Nodes
algod_client = None
indexer_client = None

# User secret key - FOR TEST PURPOSES ONLY!
user_sk = None
# User address
user_address = None
# Short form for user address
user_address_short = None

# Manager contract ID (i.e. of xGov platform)
mc_id = 0
# Escrow contract ID of connected user
ec_id = 0

# State (unique) encoding
S_INIT = 0
S_CHOOSE_USER = 1
S_TOP_MENU = 2
S_DEPLOY_NEW_XGOV = 3
S_CONNECT_TO_XGOV = 4
S_INTERACT_MANAGER = 5
S_RATIFY = 6
S_GET_PROP_STATE = 7
S_INTERACT_USER = 8
S_CREATE_PROP = 9
S_UPDATE_PROP = 10
S_ADD_STAKE = 11
S_REDUCE_STAKE = 12
S_START_SUPPORT = 13
S_REMOVE_SUPPORT = 14
S_ADD_SUPPORT = 15
S_LEAVE_XGOV = 17
S_SEND_NOTE = 18
S_CHANGE_ONLINE_STATUS = 19

# Current state
cs = -1
# Next state
ns = -1
# Previous state
ps = -1

# ---------------------------------------------------------------

# -----------------          Functions          -----------------
def init():
    global cs, ns, ps, mc_id, ec_id, user_sk, user_address, user_address_short, algod_client, indexer_client

    print("\n----------------------------------------------------------------------------------------")
    print("Welcome to xGov portal!")

# # ---- FOR TEST PURPOSES ONLY ----
#     # Algod connection parameters. Node must have EnableDeveloperAPI set to true in its config
#     algod_address = "https://node.testnet.algoexplorerapi.io"  # "http://localhost:4001"  #
#     algod_token = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
#     # Initialize an algodClient
#     algod_client = algod.AlgodClient(algod_token, algod_address)
#
#     # Indexer connection parameters.
#     indexer_address = "https://algoindexer.testnet.algoexplorerapi.io/"  # "http://localhost:8980"  #
#     indexer_token = ""
#     # Initialize an IndexerClient
#     indexer_client = indexer.IndexerClient(indexer_token, indexer_address)
# # ---- ---- ---- ---- ---- ---- ----

    while True:
        algod_address = input("First please input address to algod node to connect to: ")
        algod_token = input("Enter algod token: ")

        # Initialize an algodClient
        algod_client = algod.AlgodClient(algod_token, algod_address)

        try:
            algod_client.health()
            break
        except error.AlgodHTTPError as e:
            print("\tError: " + str(e))
            print("\tPlease try connecting to different node")

    while True:
        indexer_address = input("Please input address to indexer node to connect to: ")
        indexer_token = input("Enter indexer token: ")

        # Initialize an IndexerClient
        indexer_client = indexer.IndexerClient(indexer_token, indexer_address)

        try:
            indexer_client.health()
            break
        except error.AlgodHTTPError as e:
            print("\tError: " + str(e))
            print("\tPlease try connecting to different indexer")

    ns = S_CHOOSE_USER

    cfg.init_global_vars(algod_client)

def choose_user():
    global cs, ns, ps, mc_id, ec_id, user_sk, user_address, user_address_short, algod_client, indexer_client

    print("\n----------------------------------------------------------------------------------------")
    while True:
        path_to_m = input("Please enter path to .txt file with your wallet's mnemonic. " + \
                          "(THIS IS FOR TEST PURPOSES ONLY!): ")

        try:
            with open(path_to_m, 'r') as f:
                user_mnemonic = f.read()
                user_sk = mnemonic.to_private_key(user_mnemonic)
                user_address = account.address_from_private_key(user_sk)
                user_address_short = str(user_address[0:4]) + "..." + str(user_address[-4:])
                print("Welcome user: " + user_address_short)
            break
        except Exception:
            print("You did not enter a path to a .txt file with mnemonic!")
            continue

    ns = S_TOP_MENU

def top_menu():
    global cs, ns, ps, mc_id, ec_id, user_sk, user_address, user_address_short, algod_client, indexer_client

    print("\n----------------------------------------------------------------------------------------")
    print("Your options are:")
    print("\t1) Switch user")
    print("\t2) Create new xGov platform")
    print("\t3) Connect to existing xGov platform")
    print("\t4) Exit xGov portal")

    while True:
        c = input("Please enter number of the option you would like to choose: ")
        try:
            c = int(c)
        except ValueError:
            print("You did not enter a valid number!")
            continue

        if c == 1:
            ns = S_CHOOSE_USER
            return
        elif c == 2:
            ns = S_DEPLOY_NEW_XGOV
            return
        elif c == 3:
            ns = S_CONNECT_TO_XGOV
            return
        elif c == 4:
            exit(1)
        else:
            print("You did not enter a valid number!")
            continue

def deploy_new_xGov():
    global cs, ns, ps, mc_id, ec_id, user_sk, user_address, user_address_short, algod_client, indexer_client

    print("\n----------------------------------------------------------------------------------------")
    while True:
        print("Please enter the following parameters of the xGov platform you want to create:")

        cl = input("Commitment limit [microAlgo*round]: ")
        try:
            cl = int(cl)
        except ValueError:
            print("You did not enter a valid number!")
            continue
        fd = input("Freeze duration [round]: ")
        try:
            fd = int(fd)
        except ValueError:
            print("You did not enter a valid number!")
            continue
        ld = input("Locking duration [round]: ")
        try:
            ld = int(ld)
        except ValueError:
            print("You did not enter a valid number!")
            continue
        cp = input("Clawback percentage [%]: ")
        try:
            cp = int(cp)
        except ValueError:
            print("You did not enter a valid number!")
            continue
        pr = input("Pass rewards [microAlgo]: ")
        try:
            pr = int(pr)
        except ValueError:
            print("You did not enter a valid number!")
            continue

        try:
            print("")
            mc_id = createManager(algod_client, user_sk, cl, fd, ld, cp, pr)
            print("\nCreated xGov platform with app ID: " + str(mc_id))
            break
        except Exception as e:
            print("\tError: " + str(e))
            continue

    ns = S_INTERACT_MANAGER

def connect_to_xGov():
    global cs, ns, ps, mc_id, ec_id, user_sk, user_address, user_address_short, algod_client, indexer_client

    print("\n----------------------------------------------------------------------------------------")
    while True:
        mc_id = input("Please enter the app ID of the xGov platform you are trying to connect to: ")
        try:
            mc_id = int(mc_id)
        except ValueError:
            print("You did not enter a valid number!")
            continue

        try:
            mc_creator_address = algod_client.application_info(mc_id)["params"]["creator"]
        except error.AlgodHTTPError as e:
            print("\tError: " + str(e))
            ns = ps
            return

        if mc_creator_address == user_address:
            ns = S_INTERACT_MANAGER
            print("Welcome " + user_address_short + ", xGov platform creator!")
            break
        else:
            try:
                # Get local state
                app_local = read_local_state(algod_client, user_address, mc_id)
                ec_id = app_local["ecid"]
                ns = S_INTERACT_USER
                break
            except error.AlgodHTTPError as e:
                # print("\tError: " + str(e))
                print("\tCreating xGov escrow account for user " + user_address_short + " ...")
                try:
                    joinxGov(algod_client, user_sk, mc_id)
                    app_local = read_local_state(algod_client, user_address, mc_id)
                    ec_id = app_local["ecid"]
                    ns = S_INTERACT_USER
                    break
                except error.AlgodHTTPError as e:
                    print("\tError: " + str(e))
                    print("Are you sure you are trying to connect to a valid xGov platform?")
                    continue


def manager_interact():
    global cs, ns, ps, mc_id, ec_id, user_sk, user_address, user_address_short, algod_client, indexer_client

    print("\n----------------------------------------------------------------------------------------")
    print("You are managing contract with ID " + str(mc_id) + " and following parameters:")

    while True:
        try:
            mc_state = read_global_state(algod_client, mc_id)
            print("\tCommitment limit: {} [microAlgo*round]".format(mc_state["CL"]))
            print("\tFreeze duration: {} [round]".format(mc_state["FD"]))
            print("\tLocking duration: {} [round]".format(mc_state["LD"]))
            print("\tClawback percentage: {} [%]".format(mc_state["CP"]))
            print("\tPass rewards: {} [microAlgo]".format(mc_state["PR"]))
        except error.AlgodHTTPError as e:
            print("\tError: " + str(e))
            ns = S_TOP_MENU
            break

        try:
            # Get all proposals managed by mc_id
            prop_ids = get_all_proposals_at_xGov(indexer_client, mc_id)
            print("\n\tIDs of all proposals under the xGov platform: " + str(prop_ids))
        except error.AlgodHTTPError as e:
            print("\tError: " + str(e))
            ns = S_TOP_MENU
            break

        print("\nYour options are:")
        print("\t1) Get a proposal's state")
        print("\t2) Ratify a proposal's outcome")
        print("\t3) Go to the top menu")

        while True:
            c = input("Please enter number of the option you would like to choose: ")
            try:
                c = int(c)
            except ValueError:
                print("You did not enter a valid number!")
                continue

            if c == 1:
                ns = S_GET_PROP_STATE
                return
            elif c == 2:
                ns = S_RATIFY
                return
            elif c == 3:
                ns = S_TOP_MENU
                return
            else:
                print("You did not enter a valid number!")
                continue


def ratify():
    global cs, ns, ps, mc_id, ec_id, user_sk, user_address, user_address_short, algod_client, indexer_client

    ns = ps

    print("\n----------------------------------------------------------------------------------------")
    sc_id = input("Please enter the ID of the proposal whose outcome you would like to ratify: ")
    try:
        sc_id = int(sc_id)
    except ValueError:
        print("You did not enter a valid number!")
        return

    print("Possible outcomes of the proposal are: ")
    print(str(cfg.PROP_REJECT) + ") Rejected")
    print(str(cfg.PROP_PASS) + ") Passed")
    print(str(cfg.PROP_CLAWBACK) + ") Vetoed")

    outcome = input("Please enter number of the outcome you would like to choose: ")
    try:
        outcome = int(outcome)
    except ValueError:
        print("You did not enter a valid number!")
        return

    try:
        sc_state = read_global_state(algod_client, sc_id)
        mc_state = read_global_state(algod_client, mc_id)
    except error.AlgodHTTPError as e:
        print("\tError: " + str(e))
        return

    try:
        current_round = algod_client.status().get('last-round')
        cooldown_round = sc_state["LR"] + mc_state["LD"]
        if outcome == cfg.PROP_PASS and current_round < cooldown_round:
            print("\nCan't yet ratify the proposal as passed because the cool down period hasn't passed yet")
            print("Cool down will finish at round: "  + str(cooldown_round))
            return
        else:
            print("\n\tStarting to ratify the outcome to each supporter ...\n")
            ratifyProposal(algod_client, indexer_client, user_sk, mc_id, sc_id, outcome)
    except error.AlgodHTTPError as e:
        print("\tError: " + str(e))


def get_proposal_state():
    global cs, ns, ps, mc_id, ec_id, user_sk, user_address, user_address_short, algod_client, indexer_client

    ns = ps

    print("\n----------------------------------------------------------------------------------------")
    sc_id = input("Please enter the ID of the proposal whose state you would like get: ")
    try:
        sc_id = int(sc_id)
    except ValueError:
        print("You did not enter a valid number!")
        return

    try:
        try:
            updatePropGlobalState(algod_client, user_sk, mc_id, sc_id)
        except error.AlgodHTTPError as e:
            # state is up to date
            pass
        prop_state = read_global_state(algod_client, sc_id)

        current_round = algod_client.status().get('last-round')

        print("State of the proposal at round " + str(current_round) + ":")
        if prop_state["FI"] == cfg.NOT_FINISHED:
            print("Proposal has not yet reached the commitment limit of " + str(prop_state["CL"]) + " [microAlgo*round]")
        else:
            print("Proposal has reached the commitment limit!")
        if prop_state["FR"] == cfg.FROZEN:
            print("Proposal has recently been updated and is in the review phase that will last until round " +
                  str(prop_state["LR"]+prop_state["FD"]))
        print("\tTime-weighted stake: " + str(prop_state["WS"]) + " [microAlgo*round]")
        print("\tStake: " + str(prop_state["S"]) + " [microAlgo]")

        print("\tNumber of supporters: " + str(prop_state["NS"]))

        print("\tProposer: " + str(encoding.encode_address(prop_state["P"])))
        print("\tProposal hash (SHA256): 0x" + str(prop_state["H"].hex()))

    except KeyError:
        print("Incorrect app ID - not a proposal!")
    except error.AlgodHTTPError as e:
        print("\tError: " + str(e))


def user_interact():
    global cs, ns, ps, mc_id, ec_id, user_sk, user_address, user_address_short, algod_client, indexer_client

    print("\n----------------------------------------------------------------------------------------")
    print(user_address_short + " state in xGov:")

    try:
        ec_state = read_global_state(algod_client, ec_id)
        ec_address = get_application_address(ec_id)
        ec_info = algod_client.account_info(ec_address)
        ec_balance = ec_info["amount"]
        print("\tTotal balance in xGov: {} [microAlgo]".format(ec_balance))
        print("\tEscrow account: " + str(ec_address))
        print("\tEscrow account is " + str(ec_info["status"]))
        print("\tUncommitted stake: {} [microAlgo]".format(ec_state["AS"]))
        print("\tNumber of supporting proposals: {}".format(ec_state["NSP"]))
    except error.AlgodHTTPError as e:
        print("\tError: " + str(e))
        ns = S_TOP_MENU
        return

    try:
        # Get info about all proposals supported by ec_id
        props = proposals_supported_by_user(algod_client, indexer_client, mc_id, ec_id)

        for prop in props:
            print("\t\tSupporting proposal ID " + str(prop["ID"]) + " with:")
            print("\t\t\tTime-weighted stake: " + str(prop["WS"]) + " [microAlgo*round]")
            print("\t\t\tStake: " + str(prop["S"]) + " [microAlgo*round]")
            print("\t\t\tLocal state last updated at round: " + str(prop["LR"]))
    except error.AlgodHTTPError as e:
        print("\tError: " + str(e))
        ns = S_TOP_MENU
        return

    try:
        # Get info about all proposals created by user_address
        props = proposals_created_by_user(algod_client, indexer_client, mc_id, user_address)

        print("\n\tCreated proposals with IDs: " + str(props))

    except error.AlgodHTTPError as e:
        print("\tError: " + str(e))
        ns = S_TOP_MENU
        return

    print("\nYour options are:")
    print("\t1) Get a proposal's state")
    print("\t2) Create new proposal")
    print("\t3) Update your existing proposal")
    print("\t4) Increase balance in xGov")
    print("\t5) Reduce balance in xGov")
    print("\t6) Start supporting a proposal")
    print("\t7) Add support to a proposal")
    print("\t8) Remove support of a proposal")
    print("\t9) Opt out of xGov")
    print("\t10) Register/vote in Algorand Governance with xGov escrow account")
    print("\t11) Change xGov escrow account online/offline status")
    print("\t12) Go to the top menu")

    while True:
        c = input("Please enter number of the option you would like to choose: ")
        try:
            c = int(c)
        except ValueError:
            print("You did not enter a valid number!")
            continue

        if c == 1:
            ns = S_GET_PROP_STATE
            return
        elif c == 2:
            ns = S_CREATE_PROP
            return
        elif c == 3:
            ns = S_UPDATE_PROP
            return
        elif c == 4:
            ns = S_ADD_STAKE
            return
        elif c == 5:
            ns = S_REDUCE_STAKE
            return
        elif c == 6:
            ns = S_START_SUPPORT
            return
        elif c == 7:
            ns = S_ADD_SUPPORT
            return
        elif c == 8:
            ns = S_REMOVE_SUPPORT
            return
        elif c == 9:
            ns = S_LEAVE_XGOV
            return
        elif c == 10:
            ns = S_SEND_NOTE
            return
        elif c == 11:
            ns = S_CHANGE_ONLINE_STATUS
            return
        elif c == 12:
            ns = S_TOP_MENU
            return
        else:
            print("You did not enter a valid number!")
            continue


def create_new_prop():
    global cs, ns, ps, mc_id, ec_id, user_sk, user_address, user_address_short, algod_client, indexer_client

    ns = ps

    print("\n----------------------------------------------------------------------------------------")
    print("To create a new proposal please select:")
    print("\t1) if you want to write a proposal")
    print("\t2) if you want to enter SHA256 of already written proposal")

    while True:
        c = input("Please enter number of the option you would like to choose: ")
        try:
            c = int(c)
        except ValueError:
            print("You did not enter a valid number!")
            continue

        if c==1:
            prop_txt = input("\nYour proposal: ")
            hash = bytes(bytearray.fromhex(sha256(prop_txt.encode('utf-8')).hexdigest()))
        elif c==2:
            hash = input("\nSHA256 of proposal: 0x")
            try:
                hash = int(hash, 16)
                hash = hash.to_bytes(32, 'big')
                print(hash.hex())
            except ValueError:
                print("\tYou did not enter a hexadecimal number!")
                continue
        else:
            print("You did not enter a valid number!")
            continue

        try:
            print("\nCreating a new proposal ...")
            sc_id = createProposal(algod_client, user_sk, mc_id, hash)
            print("\n\tCreated proposal with ID: " + str(sc_id))
        except error.AlgodHTTPError as e:
            print("\tError: " + str(e))
        except error.ABIEncodingError as e:
            print("\tError: " + str(e))
        return


def update_prop():
    global cs, ns, ps, mc_id, ec_id, user_sk, user_address, user_address_short, algod_client, indexer_client

    print("\n----------------------------------------------------------------------------------------")

    ns = ps

    while True:
        sc_id = input("Please enter the ID of the proposal you would like to update: ")
        try:
            sc_id = int(sc_id)
            break
        except ValueError:
            print("You did not enter a valid number!")
            continue

    try:
        prop_state = read_global_state(algod_client, sc_id)
        proposer = encoding.encode_address(prop_state["P"])
        if proposer != user_address:
            print("You can't update this proposal!")
            print("Only the initial proposer " + proposer + " can update it")
            return
    except KeyError:
        print("Incorrect app ID - not a proposal!")
        return
    except error.AlgodHTTPError as e:
        print("\tError: " + str(e))
        return

    print("To update the proposal please select:")
    print("\t1) if you want to write the update to the proposal")
    print("\t2) if you want to enter SHA256 of already updated proposal")

    while True:
        c = input("Please enter number of the option you would like to choose: ")
        try:
            c = int(c)
        except ValueError:
            print("You did not enter a valid number!")
            continue

        if c==1:
            prop_txt = input("\nYour updated proposal: ")
            hash = bytes(bytearray.fromhex(sha256(prop_txt.encode('utf-8')).hexdigest()))
        elif c==2:
            hash = input("\nSHA256 of the updated proposal: 0x")
            try:
                hash = int(hash, 16)
                hash = hash.to_bytes(32, 'big')
                print(hash.hex())
            except ValueError:
                print("\tYou did not enter a hexadecimal number!")
                continue
        else:
            print("You did not enter a valid number!")
            continue

        try:
            print("\nUpdating the proposal with ID {}... ".format(sc_id))
            updateProposal(algod_client, user_sk, mc_id, sc_id, hash)
            print("\n\tUpdated the proposal with ID: ", sc_id)
        except error.AlgodHTTPError as e:
            print("\tError: " + str(e))
        except error.ABIEncodingError as e:
            print("\tError: " + str(e))
        return


def add_stake_to_xGov():
    global cs, ns, ps, mc_id, ec_id, user_sk, user_address, user_address_short, algod_client, indexer_client

    ns = ps

    print("\n----------------------------------------------------------------------------------------")

    while True:
        amt = input("Please enter the amount [microAlgo] you would like to deposit to your xGov account: ")
        try:
            amt = int(amt)
            break
        except ValueError:
            print("You did not enter a valid number!")
            continue

    try:
        addFunds(algod_client, user_sk, mc_id, amt)
        print("\tSuccessfully added funds to xGov escrow")
    except error.AlgodHTTPError as e:
        print("\tError: " + str(e))


def reduce_stake_in_xGov():
    global cs, ns, ps, mc_id, ec_id, user_sk, user_address, user_address_short, algod_client, indexer_client

    ns = ps

    print("\n----------------------------------------------------------------------------------------")

    try:
        ec_state = read_global_state(algod_client, ec_id)
        max_withdraw_amt = ec_state["AS"]
        print("You can withdraw at most: {} [microAlgo]".format(max_withdraw_amt))
    except error.AlgodHTTPError as e:
        print("\tError: " + str(e))
        return

    while True:
        amt = input("Please enter the amount [microAlgo] you would like to withdraw from your xGov account: ")
        try:
            amt = int(amt)
            if amt > max_withdraw_amt:
                print("You can't withdraw more than the max available amount!")
                print("To withdraw more of your balance, remove support from proposals")
                continue
            break
        except ValueError:
            print("You did not enter a valid number!")
            continue

    try:
        removeFunds(algod_client, user_sk, mc_id, amt)
        print("\tSuccessfully removed funds from xGov escrow")
    except error.AlgodHTTPError as e:
        print("\tError: " + str(e))


def start_support_of_prop():
    global cs, ns, ps, mc_id, ec_id, user_sk, user_address, user_address_short, algod_client, indexer_client

    ns = ps

    print("\n----------------------------------------------------------------------------------------")

    while True:
        sc_id = input("Please enter the ID of the proposal you would like to start supporting: ")
        try:
            sc_id = int(sc_id)
            break
        except ValueError:
            print("You did not enter a valid number!")
            continue

    try:
        prop_state = read_global_state(algod_client, sc_id)
        prop_mc_id = prop_state["MAID"]
        if prop_mc_id != mc_id:
            print("This app is not managed by this xGov platform")
            return

        if prop_state["FI"] == cfg.FINISHED:
            print("You can't start supporting this proposal because it has already reached the commitment limit.")
            return

        props = proposals_supported_by_user(algod_client, indexer_client, mc_id, ec_id)

        if sc_id in [prop["ID"] for prop in props]:
            print("You are already supporting this proposal")
            return
    except KeyError:
        print("Incorrect app ID - not a proposal!")
        return
    except error.AlgodHTTPError as e:
        print("\tError: " + str(e))
        return

    try:
        startSupportingProp(algod_client, user_sk, mc_id, sc_id)
        print("\tSuccessfully started supporting proposal with ID: " + str(sc_id))
    except error.AlgodHTTPError as e:
        print("\tError: " + str(e))


def remove_support_of_prop():
    global cs, ns, ps, mc_id, ec_id, user_sk, user_address, user_address_short, algod_client, indexer_client

    ns = ps

    print("\n----------------------------------------------------------------------------------------")

    while True:
        sc_id = input("Please enter the ID of the proposal you would like to stop supporting: ")
        try:
            sc_id = int(sc_id)
            break
        except ValueError:
            print("You did not enter a valid number!")
            continue

    try:
        prop_state = read_global_state(algod_client, sc_id)
        prop_mc_id = prop_state["MAID"]
        if prop_mc_id != mc_id:
            print("This app is not managed by this xGov platform")
            return

        if prop_state["FI"] == cfg.FINISHED:
            print("You can't withdraw the support because the proposal has reached the commitment limit.")
            print("Wait for the xGov manager to ratify the outcome of the proposal's vote")
            return

        props = proposals_supported_by_user(algod_client, indexer_client, mc_id, ec_id)

        if sc_id not in [prop["ID"] for prop in props]:
            print("You are not supporting this proposal")
            return

    except KeyError:
        print("Incorrect app ID - not a proposal!")
        return
    except error.AlgodHTTPError as e:
        print("\tError: " + str(e))
        return

    try:
        removeSupportOfProp(algod_client, user_sk, mc_id, sc_id)
        print("\tSuccessfully stopped supporting proposal with ID: " + str(sc_id))
    except error.AlgodHTTPError as e:
        print("\tError: " + str(e))


def add_support_to_prop():
    global cs, ns, ps, mc_id, ec_id, user_sk, user_address, user_address_short, algod_client, indexer_client

    ns = ps

    print("\n----------------------------------------------------------------------------------------")

    while True:
        sc_id = input("Please enter the ID of the proposal you would like to give additional support to: ")
        try:
            sc_id = int(sc_id)
            break
        except ValueError:
            print("You did not enter a valid number!")
            continue

    try:
        prop_state = read_global_state(algod_client, sc_id)
        prop_mc_id = prop_state["MAID"]
        if prop_mc_id != mc_id:
            print("This app is not managed by this xGov platform")
            return

        if prop_state["FI"] == cfg.FINISHED:
            print("You can't add support to this proposal because it has already reached the commitment limit.")
            return

        props = proposals_supported_by_user(algod_client, indexer_client, mc_id, ec_id)

        if sc_id not in [prop["ID"] for prop in props]:
            print("You are not supporting this proposal. Start supporting it first.")
            return

    except KeyError:
        print("Incorrect app ID - not a proposal!")
        return
    except error.AlgodHTTPError as e:
        print("\tError: " + str(e))
        return

    try:
        ec_state = read_global_state(algod_client, ec_id)
        max_support_amt = ec_state["AS"]
        print("You can give at most {} [microAlgo] to the support of the proposal".format(max_support_amt))
    except error.AlgodHTTPError as e:
        print("\tError: " + str(e))
        return

    while True:
        amt = input("Please enter the amount in [microAlgo] you would like to give to the support of the proposal: ")
        try:
            amt = int(amt)
            if amt > max_support_amt:
                print("You can't add more support than you have available.")
                print("You can't either remove support from your other proposals or deposit additional funds to xGov.")
                return
            break
        except ValueError:
            print("You did not enter a valid number!")
            continue

    try:
        addSupportToProp(algod_client, user_sk, mc_id, sc_id, amt)
        print("\tSuccessfully add support to the proposal")
    except error.AlgodHTTPError as e:
        print("\tError: " + str(e))


def leave_xGov():
    global cs, ns, ps, mc_id, ec_id, user_sk, user_address, user_address_short, algod_client, indexer_client

    ns = ps

    print("\n----------------------------------------------------------------------------------------")

    try:
        ec_state = read_global_state(algod_client, ec_id)
        number_of_proposals_user_supports = ec_state["NSP"]

        if number_of_proposals_user_supports > 0:
            print("You are still supporting {} proposals".format(number_of_proposals_user_supports))
            print("If you leave xGov now, you will forfeit all your stake in xGov!")
            print("Please consider removing your support of proposals first.")

            while True:
                c = input("\nDo you really want to forfeit your stake in xGov and opt out [Y/N]? ")
                if c == "Y":
                    forceQuitxGov(algod_client, user_sk, mc_id)
                    print("\n\tSuccessfully exited xGov")
                    ns = S_TOP_MENU
                    return
                elif c == "N":
                    return
                else:
                    print("\tIncorrect value")
                    continue

        else:
            leavexGov(algod_client, user_sk, mc_id)
            print("\n\tSuccessfully opted out of xGov")
            ns = S_TOP_MENU
            return
    except error.AlgodHTTPError as e:
        print("\tError: " + str(e))
        return


def send_note():
    global cs, ns, ps, mc_id, ec_id, user_sk, user_address, user_address_short, algod_client, indexer_client

    ns = ps

    print("\n----------------------------------------------------------------------------------------")
    print("Before proceeding, make sure to check: ")
    print("\t https://github.com/algorandfoundation/governance/blob/main/af-gov1-spec.md ")
    print("\t https://governance.algorand.foundation/ ")
    print("")

    msg = input("Please enter the message according to Algorand Governance structure: ")
    gov_address = input("Please enter the Algorand Governance address [58 char]: ")

    try:
        print("")
        sendNote(algod_client, user_sk, mc_id, gov_address, msg)
        print("\n\tSuccessfully opted out of xGov")
    except error.AlgodHTTPError as e:
        print("\tError: " + str(e))

    return


def change_online_status():
    global cs, ns, ps, mc_id, ec_id, user_sk, user_address, user_address_short, algod_client, indexer_client

    ns = ps

    print("\n----------------------------------------------------------------------------------------")


    try:
        ec_address = get_application_address(ec_id)
        ec_info = algod_client.account_info(ec_address)

        if ec_info["status"] == "Offline":
            print("Please enter the required information for brining account online")

            votekey = input("Voting key: ")
            selkey  = input("Selection key: ")
            sprfkey = input("State proof key: ")
            votefst = input("Vote first round: ")
            votefst = int(votefst)
            votelst = input("Vote last round: ")
            votelst = int(votelst)
            votekd = input("Vote key dilution: ")
            votekd = int(votekd)

            print("")
            bringOnline(algod_client, user_sk, mc_id, votekey, selkey, sprfkey, votefst, votelst, votekd)
            print("\n\tSuccessfully brought escrow account online")
        elif ec_info["status"] == "Online":
            print("")
            bringOffline(algod_client, user_sk, mc_id)
            print("\n\tSuccessfully brought escrow account offline")
        else:
            print("Error: Invalid account status")
            return
    except ValueError:
        return
    except error.AlgodHTTPError as e:
        print("\tError: " + str(e))

    return


# ---------------------------------------------------------------

def main():

    global cs, ns, ps, mc_id, ec_id, user_sk, user_address, user_address_short, algod_client, indexer_client

    cs = S_INIT

    while True:

        if cs == S_INIT:
            init()
        elif cs == S_CHOOSE_USER:
            choose_user()
        elif cs == S_TOP_MENU:
            top_menu()
        elif cs == S_DEPLOY_NEW_XGOV:
            deploy_new_xGov()
        elif cs == S_CONNECT_TO_XGOV:
            connect_to_xGov()
        elif cs == S_INTERACT_MANAGER:
            manager_interact()
        elif cs == S_RATIFY:
            ratify()
        elif cs == S_GET_PROP_STATE:
            get_proposal_state()
        elif cs == S_INTERACT_USER:
            user_interact()
        elif cs == S_CREATE_PROP:
            create_new_prop()
        elif cs == S_UPDATE_PROP:
            update_prop()
        elif cs == S_ADD_STAKE:
            add_stake_to_xGov()
        elif cs == S_REDUCE_STAKE:
            reduce_stake_in_xGov()
        elif cs == S_START_SUPPORT:
            start_support_of_prop()
        elif cs == S_REMOVE_SUPPORT:
            remove_support_of_prop()
        elif cs == S_ADD_SUPPORT:
            add_support_to_prop()
        elif cs == S_LEAVE_XGOV:
            leave_xGov()
        elif cs == S_SEND_NOTE:
            send_note()
        elif cs == S_CHANGE_ONLINE_STATUS:
            change_online_status()
        else:
            raise ValueError('Invalid state')

        ps = cs
        cs = ns



if __name__ == "__main__":
    main()
