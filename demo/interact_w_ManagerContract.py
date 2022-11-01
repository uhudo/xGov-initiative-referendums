# -----------------           Imports          -----------------
import base64
import math
from hashlib import sha256
import glob
from time import sleep
from algosdk.v2client import algod, indexer
from algosdk.future import transaction
from algosdk import account, mnemonic, error
from algosdk.abi import Contract
from algosdk import encoding
from algosdk.atomic_transaction_composer import AtomicTransactionComposer, AccountTransactionSigner, \
    TransactionWithSigner
from algosdk.logic import get_application_address
from util import *

import src.config as cfg

# ---------------------------------------------------------------

def joinxGov(
    algod_client: algod.AlgodClient,
    userSK: str,
    MC_ID: int,
):
    # Get user address
    user_address = account.address_from_private_key(userSK)

    # Get manager contract address
    manager_address = get_application_address(MC_ID)

    sp = algod_client.suggested_params()

    atc = AtomicTransactionComposer()
    signer = AccountTransactionSigner(userSK)

    sp.flat_fee = True
    sp.fee = 3 * sp.min_fee

    # Send sufficient funds to MC for opt-in
    payTxn = transaction.PaymentTxn(
        sender=user_address,
        receiver=manager_address,
        amt=cfg.EC_FUNDING_FOR_CREATION,
        sp=sp
    )
    tws = TransactionWithSigner(payTxn, signer)
    atc.add_transaction(tws)

    sp.fee = 0

    # Opt-in to MC
    optInTxn = transaction.ApplicationOptInTxn(
        sender=user_address,
        index=MC_ID,
        sp=sp
    )
    tws = TransactionWithSigner(optInTxn, signer)
    atc.add_transaction(tws)

    result = atc.execute(algod_client, 10)

    for res in result.tx_ids:
        print("\tTx ID: " + res)

    # Get the ID of the escrow that was created for the user
    app_local = read_local_state(algod_client, user_address, MC_ID)
    try:
        print("\tEscrow with App ID: {} was created for user {}".format(app_local["ecid"], user_address))
    except KeyError:
        print("\tNo escrow was created")


def createProposal(
    algod_client: algod.AlgodClient,
    userSK: str,
    MC_ID: int,
    hash: bytes,
):
    sp = algod_client.suggested_params()

    user_address = account.address_from_private_key(userSK)
    manager_address = get_application_address(MC_ID)

    with open("./compiled_files/ManagerContract.json", "r") as f:
        import json
        js = f.read()

    contract = Contract.from_json(js)

    method = contract.get_method_by_name("new_proposal")
    app_args = [
        hash
    ]

    atc = AtomicTransactionComposer()
    signer = AccountTransactionSigner(userSK)

    sp.flat_fee = True
    sp.fee = 4*sp.min_fee

    fund_tx = transaction.PaymentTxn(
        sender=user_address,
        sp=sp,
        receiver=manager_address,
        amt=cfg.SC_FUNDING_FOR_CREATION+cfg.SC_FUNDING_FOR_OPTIN,
    )
    tws = TransactionWithSigner(fund_tx, signer)
    atc.add_transaction(tws)

    sp.fee = 0

    atc.add_method_call(
        app_id=MC_ID,
        method=method,
        sender=user_address,
        sp=sp,
        signer=signer,
        method_args=app_args,
        foreign_apps=None
    )

    result = atc.execute(algod_client, 10)

    for res in result.tx_ids:
        print("\tTx ID: " + res)

    for res in result.abi_results:
        ret_val = res.return_value
        print("\tReturn value: " + str(ret_val))

    return result.abi_results[0].return_value

def updateProposal(
    algod_client: algod.AlgodClient,
    proposerSK: str,
    MC_ID: int,
    PROP_ID: int,
    newHash: bytes,
):
    sp = algod_client.suggested_params()

    proposer_address = account.address_from_private_key(proposerSK)

    with open("./compiled_files/ManagerContract.json", "r") as f:
        import json
        js = f.read()

    contract = Contract.from_json(js)

    method = contract.get_method_by_name("proposal_update")
    app_args = [
        newHash
    ]

    atc = AtomicTransactionComposer()
    signer = AccountTransactionSigner(proposerSK)

    sp.flat_fee = True
    sp.fee = 2*sp.min_fee

    atc.add_method_call(
        app_id=MC_ID,
        method=method,
        sender=proposer_address,
        sp=sp,
        signer=signer,
        method_args=app_args,
        foreign_apps=[PROP_ID]
    )

    result = atc.execute(algod_client, 10)

    for res in result.tx_ids:
        print("\tTx ID: " + res)

def updatePropGlobalState(
    algod_client: algod.AlgodClient,
    userSK: str,
    MC_ID: int,
    PROP_ID: int,
):
    sp = algod_client.suggested_params()

    user_address = account.address_from_private_key(userSK)

    with open("./compiled_files/ManagerContract.json", "r") as f:
        import json
        js = f.read()

    contract = Contract.from_json(js)

    method = contract.get_method_by_name("update_prop_global_state")
    app_args = []

    atc = AtomicTransactionComposer()
    signer = AccountTransactionSigner(userSK)

    sp.flat_fee = True
    sp.fee = 2*sp.min_fee

    atc.add_method_call(
        app_id=MC_ID,
        method=method,
        sender=user_address,
        sp=sp,
        signer=signer,
        method_args=app_args,
        foreign_apps=[PROP_ID]
    )

    result = atc.execute(algod_client, 10)

    for res in result.tx_ids:
        print("\tTx ID: " + res)


def ratifyProposal(
    algod_client: algod.AlgodClient,
    indexer_client: indexer.IndexerClient,
    creatorSK: str,
    MC_ID: int,
    PROP_ID: int,
    outcome: int,
):

    sp = algod_client.suggested_params()

    creator_address = account.address_from_private_key(creatorSK)

    # Get manager contract address
    manager_address = get_application_address(MC_ID)

    # Check if proposal is finished
    prop_state = read_global_state(algod_client, PROP_ID)
    prop_finished = prop_state["FI"]
    if prop_finished == cfg.NOT_FINISHED:
        print("\tCan't ratify proposal because it isn't finished yet")
        return

    # If the proposal passed, ensure the manager contract has enough funds for the promised rewards
    if outcome == cfg.PROP_PASS:
        # Get the promised rewards for passing
        amt = read_global_state(algod_client, MC_ID)["PR"]
        # Get the manager available balance
        manager_info = algod_client.account_info(manager_address)
        manager_available_balance = manager_info["amount"] - manager_info["min-balance"]
        if amt-manager_available_balance > 0:
            atc = AtomicTransactionComposer()
            signer = AccountTransactionSigner(creatorSK)
            # Send sufficient funds to MC for payout of promised rewards
            payTxn = transaction.PaymentTxn(
                sender=creator_address,
                receiver=manager_address,
                amt=amt-manager_available_balance,
                sp=sp
            )
            tws = TransactionWithSigner(payTxn, signer)
            atc.add_transaction(tws)

            result = atc.execute(algod_client, 10)

            for res in result.tx_ids:
                print("\tTx ID: " + res)

        print("\tManager has sufficient funds for payout of rewards")

    # Get all contracts
    cs = []
    nexttoken = ""
    num_apps = 1
    # loop using next_page to paginate until there are no more apps in the response
    while (num_apps > 0):
        response = indexer_client.lookup_account_application_by_creator(address=manager_address, next_page=nexttoken)
        apps = response['applications']
        app_ids = [app['id'] for app in apps]
        cs = cs + app_ids
        num_apps = len(apps)
        if (num_apps > 0):
            nexttoken = response['next-token']

    # print(cs)

    # Prepare method call
    with open("./compiled_files/ManagerContract.json", "r") as f:
        import json
        js = f.read()
    contract = Contract.from_json(js)
    method = contract.get_method_by_name("ratify")
    app_args = [
        outcome
    ]
    sp.flat_fee = True
    # Fee for ratification depends on outcome
    if outcome == cfg.PROP_PASS:
        sp.fee = 5 * sp.min_fee
    elif outcome == cfg.PROP_CLAWBACK:
        sp.fee = 4 * sp.min_fee
    elif outcome == cfg.PROP_REJECT:
        sp.fee = 3 * sp.min_fee
    else:
        print("\tIncorrect outcome!")
        return

    c_val = None

    # For each contract, try to ratify it (some will fail because they are SCs, others are not interacting with sc_id)
    for c in cs:
        try:
            # Get escrow owner
            app_local = read_global_state(algod_client, c)
            ec_owner = encoding.encode_address(app_local["Owner"])
            print("\tEscrow id: {}, owner: {}".format(c, ec_owner))

            atc = AtomicTransactionComposer()
            signer = AccountTransactionSigner(creatorSK)
            # Send ratification call
            atc.add_method_call(
                app_id=MC_ID,
                method=method,
                sender=creator_address,
                sp=sp,
                signer=signer,
                method_args=app_args,
                accounts=[ec_owner],
                foreign_apps=[PROP_ID, c]
            )

            result = atc.execute(algod_client, 10)

            for res in result.tx_ids:
                print("\tTx ID: " + res)

            c_val = c

        except error.AlgodHTTPError as e:
            print("\tError: " + str(e))

        except Exception:
            continue

    if c_val is not None:
        print("\n\tFinished ratifying accounts\n")
    else:
        print("\n\tError with ratification!")
        return

    # All accounts should be ratified now, thus proposal can be deleted
    try:
        # Check if there are any funds in the contract account - in which case there will be a close Tx, thus higher fee
        bal = algod_client.account_info(get_application_address(PROP_ID))["amount"]
        if bal > 0:
            sp.fee = (3+0) * sp.min_fee
        else:
            sp.fee = (2+0) * sp.min_fee
        atc = AtomicTransactionComposer()
        signer = AccountTransactionSigner(creatorSK)
        # Send ratification call
        atc.add_method_call(
            app_id=MC_ID,
            method=method,
            sender=creator_address,
            sp=sp,
            signer=signer,
            method_args=app_args,
            foreign_apps=[PROP_ID, c_val]   # Have to submit an escrow as 2nd app even though not used - to improve
        )

        result = atc.execute(algod_client, 10)

        for res in result.tx_ids:
            print("\tTx ID: " + res)

        print("\tDeleted proposal with ID: " + str(PROP_ID))
    except error.AlgodHTTPError as e:
        print("\tError: " + str(e))
        return

    print("\nSuccessfully ratified the proposal")


def leavexGov(
    algod_client: algod.AlgodClient,
    userSK: str,
    MC_ID: int,
):
    # Get user address
    user_address = account.address_from_private_key(userSK)

    # Get user escrow ID
    app_local = read_local_state(algod_client, user_address, MC_ID)
    ec_id = app_local["ecid"]

    # Get escrow balance
    ec_balance = algod_client.account_info(get_application_address(ec_id))["amount"]

    sp = algod_client.suggested_params()

    sp.flat_fee = True
    if ec_balance > 0:
        # balance needs to be closed, meaning there is one more transaction
        sp.fee = 3 * sp.min_fee
    else:
        sp.fee = 2 * sp.min_fee

    atc = AtomicTransactionComposer()
    signer = AccountTransactionSigner(userSK)

    # Opt out of MC
    closeOutTxn = transaction.ApplicationCloseOutTxn(
        sender=user_address,
        index=MC_ID,
        sp=sp,
        foreign_apps=[ec_id]
    )
    tws = TransactionWithSigner(closeOutTxn, signer)
    atc.add_transaction(tws)

    result = atc.execute(algod_client, 10)

    for res in result.tx_ids:
        print("\tTx ID: " + res)


def forceQuitxGov(
    algod_client: algod.AlgodClient,
    userSK: str,
    MC_ID: int,
):
    # Get user address
    user_address = account.address_from_private_key(userSK)

    sp = algod_client.suggested_params()

    atc = AtomicTransactionComposer()
    signer = AccountTransactionSigner(userSK)

    # Clear state of MC
    clearStateTxn = transaction.ApplicationClearStateTxn(
        sender=user_address,
        index=MC_ID,
        sp=sp
    )
    tws = TransactionWithSigner(clearStateTxn, signer)
    atc.add_transaction(tws)

    result = atc.execute(algod_client, 10)

    for res in result.tx_ids:
        print("\tTx ID: " + res)


def startSupportingProp(
    algod_client: algod.AlgodClient,
    userSK: str,
    MC_ID: int,
    PROP_ID: int,
):
    sp = algod_client.suggested_params()

    # Get user address
    user_address = account.address_from_private_key(userSK)

    # Get user escrow ID
    app_local = read_local_state(algod_client, user_address, MC_ID)
    ec_id = app_local["ecid"]

    # Get escrow address
    ec_address = get_application_address(ec_id)

    # Get escrow balance
    ec_balance = algod_client.account_info(get_application_address(ec_id))["amount"]

    with open("./compiled_files/ManagerContract.json", "r") as f:
        import json
        js = f.read()

    contract = Contract.from_json(js)

    method = contract.get_method_by_name("start_supporting_prop")
    app_args = []

    atc = AtomicTransactionComposer()
    signer = AccountTransactionSigner(userSK)

    sp.flat_fee = True
    sp.fee = 4*sp.min_fee

    # Send sufficient funds to escrow for opting into the proposal
    if ec_balance > 0:
        amt = cfg.SC_FUNDING_FOR_OPTIN
    else:
        # If escrow is empty, it is necessary to fund it besides sending opt-in fees
        amt = cfg.SC_FUNDING_FOR_OPTIN + 100_000

    payTxn = transaction.PaymentTxn(
        sender=user_address,
        receiver=ec_address,
        amt=amt,
        sp=sp
    )
    tws = TransactionWithSigner(payTxn, signer)
    atc.add_transaction(tws)

    sp.fee = 0

    atc.add_method_call(
        app_id=MC_ID,
        method=method,
        sender=user_address,
        sp=sp,
        signer=signer,
        method_args=app_args,
        foreign_apps=[PROP_ID, ec_id]
    )

    result = atc.execute(algod_client, 10)

    for res in result.tx_ids:
        print("\tTx ID: " + res)


def removeSupportOfProp(
    algod_client: algod.AlgodClient,
    userSK: str,
    MC_ID: int,
    PROP_ID: int,
):
    sp = algod_client.suggested_params()

    # Get user address
    user_address = account.address_from_private_key(userSK)

    # Get user escrow ID
    app_local = read_local_state(algod_client, user_address, MC_ID)
    ec_id = app_local["ecid"]

    with open("./compiled_files/ManagerContract.json", "r") as f:
        import json
        js = f.read()

    contract = Contract.from_json(js)

    method = contract.get_method_by_name("remove_support_from_prop")
    app_args = []

    atc = AtomicTransactionComposer()
    signer = AccountTransactionSigner(userSK)

    sp.flat_fee = True
    sp.fee = 3*sp.min_fee

    atc.add_method_call(
        app_id=MC_ID,
        method=method,
        sender=user_address,
        sp=sp,
        signer=signer,
        method_args=app_args,
        foreign_apps=[PROP_ID, ec_id]
    )

    result = atc.execute(algod_client, 10)

    for res in result.tx_ids:
        print("\tTx ID: " + res)

def addFunds(
    algod_client: algod.AlgodClient,
    userSK: str,
    MC_ID: int,
    amount: int,
):
    sp = algod_client.suggested_params()

    # Get user address
    user_address = account.address_from_private_key(userSK)

    # Get user escrow ID
    app_local = read_local_state(algod_client, user_address, MC_ID)
    ec_id = app_local["ecid"]

    # Get escrow address
    ec_address = get_application_address(ec_id)

    with open("./compiled_files/ManagerContract.json", "r") as f:
        import json
        js = f.read()

    contract = Contract.from_json(js)

    method = contract.get_method_by_name("add_funds")
    app_args = []

    atc = AtomicTransactionComposer()
    signer = AccountTransactionSigner(userSK)

    sp.flat_fee = True
    sp.fee = 3*sp.min_fee

    payTxn = transaction.PaymentTxn(
        sender=user_address,
        receiver=ec_address,
        amt=amount,
        sp=sp
    )
    tws = TransactionWithSigner(payTxn, signer)
    atc.add_transaction(tws)

    sp.fee = 0

    atc.add_method_call(
        app_id=MC_ID,
        method=method,
        sender=user_address,
        sp=sp,
        signer=signer,
        method_args=app_args,
        foreign_apps=[ec_id]
    )

    result = atc.execute(algod_client, 10)

    for res in result.tx_ids:
        print("\tTx ID: " + res)


def removeFunds(
    algod_client: algod.AlgodClient,
    userSK: str,
    MC_ID: int,
    amount: int,
):
    sp = algod_client.suggested_params()

    # Get user address
    user_address = account.address_from_private_key(userSK)

    # Get user escrow ID
    app_local = read_local_state(algod_client, user_address, MC_ID)
    ec_id = app_local["ecid"]

    with open("./compiled_files/ManagerContract.json", "r") as f:
        import json
        js = f.read()

    contract = Contract.from_json(js)

    method = contract.get_method_by_name("remove_funds")
    app_args = [
        amount
    ]

    atc = AtomicTransactionComposer()
    signer = AccountTransactionSigner(userSK)

    sp.flat_fee = True
    sp.fee = 3*sp.min_fee

    atc.add_method_call(
        app_id=MC_ID,
        method=method,
        sender=user_address,
        sp=sp,
        signer=signer,
        method_args=app_args,
        foreign_apps=[ec_id]
    )

    result = atc.execute(algod_client, 10)

    for res in result.tx_ids:
        print("\tTx ID: " + res)


def addSupportToProp(
    algod_client: algod.AlgodClient,
    userSK: str,
    MC_ID: int,
    PROP_ID: int,
    amount: int,
):
    sp = algod_client.suggested_params()

    # Get user address
    user_address = account.address_from_private_key(userSK)

    # Get user escrow ID
    app_local = read_local_state(algod_client, user_address, MC_ID)
    ec_id = app_local["ecid"]

    with open("./compiled_files/ManagerContract.json", "r") as f:
        import json
        js = f.read()

    contract = Contract.from_json(js)

    method = contract.get_method_by_name("add_support_to_prop")
    app_args = [
        amount
    ]

    atc = AtomicTransactionComposer()
    signer = AccountTransactionSigner(userSK)

    sp.flat_fee = True
    sp.fee = 3*sp.min_fee

    atc.add_method_call(
        app_id=MC_ID,
        method=method,
        sender=user_address,
        sp=sp,
        signer=signer,
        method_args=app_args,
        foreign_apps=[PROP_ID, ec_id]
    )

    result = atc.execute(algod_client, 10)

    for res in result.tx_ids:
        print("\tTx ID: " + res)

def createManager(
    algod_client: algod.AlgodClient,
    creatorSK: str,
    commitLimit: int,
    frozenDuration: int,
    lockingDuration: int,
    clawbackPercentage: int,
    passRewards: int,
):
    creator_address = account.address_from_private_key(creatorSK)

    # Declare application state storage (immutable)
    global_schema = transaction.StateSchema(cfg.MC_NUM_GLOBAL_UINT, cfg.MC_NUM_GLOBAL_BYTES)
    local_schema = transaction.StateSchema(cfg.MC_NUM_LOCAL_UINT, cfg.MC_NUM_LOCAL_BYTES)

    app_args = [
        commitLimit,
        frozenDuration,
        lockingDuration,
        clawbackPercentage,
        passRewards
    ]

    sp = algod_client.suggested_params()
    atc = AtomicTransactionComposer()
    signer = AccountTransactionSigner(creatorSK)

    # Simple call to the `create_app` method, method_args can be any type but _must_
    # match those in the method signature of the contract
    atc.add_method_call(
        app_id=0,
        method=cfg.MC_contract.get_method_by_name("create_app"),
        sender=creator_address,
        sp=sp,
        signer=signer,
        approval_program=cfg.MC_approval_program,
        clear_program=cfg.MC_clear_state_program,
        local_schema=local_schema,
        global_schema=global_schema,
        method_args=app_args,
        extra_pages=cfg.MC_ExtraProgramPages,
        foreign_apps=None
    )

    result = atc.execute(algod_client, 10)
    app_id = transaction.wait_for_confirmation(algod_client, result.tx_ids[0])['application-index']

    for res in result.tx_ids:
        print("\tTx ID: " + res)

    assert app_id is not None and app_id > 0

    # Fund the manager account with 0.1 ALGO
    MA_addr = get_application_address(app_id)
    fundTx = transaction.PaymentTxn(
        sender=creator_address,
        sp=sp,
        receiver=MA_addr,
        amt=100_000,
    )
    signedFundingTxn = fundTx.sign(creatorSK)
    algod_client.send_transaction(signedFundingTxn)
    transaction.wait_for_confirmation(algod_client, signedFundingTxn.get_txid())

    print("\tTx ID: " + signedFundingTxn.get_txid())

    return app_id

def get_all_proposals_at_xGov(indexer_client, MC_ID):
    # Get manager contract address
    manager_address = get_application_address(MC_ID)

    # Get all contracts created by the manager
    app_ids = []
    nexttoken = ""
    num_apps = 1
    # loop using next_page to paginate until there are no more apps in the response
    while (num_apps > 0):
        response = indexer_client.lookup_account_application_by_creator(address=manager_address, next_page=nexttoken)
        apps = response['applications']
        for app in apps:
            # Check if app is SC or EC by checking the local-state-schema (the former doesn't have any)
            if app["params"]["local-state-schema"]["num-uint"] != 0:
                app_ids.append(app["id"])

        num_apps = len(apps)
        if (num_apps > 0):
            nexttoken = response['next-token']

    return app_ids


def proposals_created_by_user(algod_client, indexer_client, MC_ID, user_address):
    # Get manager contract address
    manager_address = get_application_address(MC_ID)

    # Get all contracts created by the manager
    app_ids = []
    nexttoken = ""
    num_apps = 1
    # loop using next_page to paginate until there are no more apps in the response
    while (num_apps > 0):
        response = indexer_client.lookup_account_application_by_creator(address=manager_address, next_page=nexttoken)
        apps = response['applications']
        for app in apps:
            # Check if app is SC or EC by checking the local-state-schema (the former doesn't have any)
            if app["params"]["local-state-schema"]["num-uint"] != 0:
                # Get the app global state
                prop_state = read_global_state(algod_client, app["id"])
                # Check if proposer is the user_address
                if encoding.encode_address(prop_state["P"]) == user_address:
                    app_ids.append(app["id"])

        num_apps = len(apps)
        if (num_apps > 0):
            nexttoken = response['next-token']

    return app_ids


def proposals_supported_by_user(algod_client, indexer_client, MC_ID, EC_ID):
    # Get manager contract address
    manager_address = get_application_address(MC_ID)

    # Get escrow contract address
    ec_address = get_application_address(EC_ID)

    # Get all contracts created by the manager
    props = []
    nexttoken = ""
    num_apps = 1
    # loop using next_page to paginate until there are no more apps in the response
    while (num_apps > 0):
        response = indexer_client.lookup_account_application_by_creator(address=manager_address, next_page=nexttoken)
        apps = response['applications']
        for app in apps:
            # Check if app is SC or EC by checking the local-state-schema (the former doesn't have any)
            if app["params"]["local-state-schema"]["num-uint"] != 0:
                app_id = app["id"]
                try:
                    # Get the app's local state for the user_address
                    prop_local_state = read_local_state(algod_client, ec_address, app_id)
                    prop = {
                        "ID": app_id,
                        "WS": prop_local_state["WS"],
                        "S": prop_local_state["S"],
                        "LR": prop_local_state["LR"],
                    }
                    props.append(prop)
                except Exception:
                    pass

        num_apps = len(apps)
        if (num_apps > 0):
            nexttoken = response['next-token']

    return props


def sendNote(
    algod_client: algod.AlgodClient,
    userSK: str,
    MC_ID: int,
    rcv: str,
    msg: str,
):
    sp = algod_client.suggested_params()

    # Get user address
    user_address = account.address_from_private_key(userSK)

    # Get user escrow ID
    app_local = read_local_state(algod_client, user_address, MC_ID)
    ec_id = app_local["ecid"]

    with open("./compiled_files/ManagerContract.json", "r") as f:
        import json
        js = f.read()

    contract = Contract.from_json(js)

    method = contract.get_method_by_name("send_note")
    app_args = [
        rcv,
        msg.encode()
    ]

    atc = AtomicTransactionComposer()
    signer = AccountTransactionSigner(userSK)

    sp.flat_fee = True
    sp.fee = 3 * sp.min_fee

    atc.add_method_call(
        app_id=MC_ID,
        method=method,
        sender=user_address,
        sp=sp,
        signer=signer,
        method_args=app_args,
        foreign_apps=[ec_id],
        accounts=[rcv]
    )

    result = atc.execute(algod_client, 10)

    for res in result.tx_ids:
        print("\tTx ID: " + res)

def bringOnline(
    algod_client: algod.AlgodClient,
    userSK: str,
    MC_ID: int,
    votekey: str,
    selkey: str,
    sprfkey: str,
    votefst: int,
    votelst: int,
    votekd: int
):
    sp = algod_client.suggested_params()

    # Get user address
    user_address = account.address_from_private_key(userSK)

    # Get user escrow ID
    app_local = read_local_state(algod_client, user_address, MC_ID)
    ec_id = app_local["ecid"]

    with open("./compiled_files/ManagerContract.json", "r") as f:
        import json
        js = f.read()

    contract = Contract.from_json(js)

    votekey_arg = base64.b64decode(votekey)
    selkey_arg = base64.b64decode(selkey)
    sprfkey_arg = base64.b64decode(sprfkey)

    method = contract.get_method_by_name("bring_online")
    app_args = [
        votekey_arg,
        selkey_arg,
        sprfkey_arg,
        votefst,
        votelst,
        votekd
    ]

    atc = AtomicTransactionComposer()
    signer = AccountTransactionSigner(userSK)

    sp.flat_fee = True
    sp.fee = 3 * sp.min_fee

    atc.add_method_call(
        app_id=MC_ID,
        method=method,
        sender=user_address,
        sp=sp,
        signer=signer,
        method_args=app_args,
        foreign_apps=[ec_id]
    )

    result = atc.execute(algod_client, 10)

    for res in result.tx_ids:
        print("\tTx ID: " + res)


def bringOffline(
    algod_client: algod.AlgodClient,
    userSK: str,
    MC_ID: int,
):
    sp = algod_client.suggested_params()

    # Get user address
    user_address = account.address_from_private_key(userSK)

    # Get user escrow ID
    app_local = read_local_state(algod_client, user_address, MC_ID)
    ec_id = app_local["ecid"]

    with open("./compiled_files/ManagerContract.json", "r") as f:
        import json
        js = f.read()

    contract = Contract.from_json(js)

    method = contract.get_method_by_name("bring_offline")
    app_args = []

    atc = AtomicTransactionComposer()
    signer = AccountTransactionSigner(userSK)

    sp.flat_fee = True
    sp.fee = 3 * sp.min_fee

    atc.add_method_call(
        app_id=MC_ID,
        method=method,
        sender=user_address,
        sp=sp,
        signer=signer,
        method_args=app_args,
        foreign_apps=[ec_id]
    )

    result = atc.execute(algod_client, 10)

    for res in result.tx_ids:
        print("\tTx ID: " + res)

