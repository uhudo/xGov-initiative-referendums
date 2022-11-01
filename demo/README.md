# Video Demo

The video excerpts below demonstrate an example scenario of interactions of three accounts `a`, `b`, and `c` with the 
xGov platform through the provided interaction [script](../interaction_state_machine.py).

When running the script, [REST endpoints](https://developer.algorand.org/docs/rest-apis/restendpoints/) for Algorand 
protocol daemon and Algorand Indexer daemon first need to be entered. Connections via 
[AlgoExplorer](https://testnet.algoexplorer.io/) to the Algorand Testnet are established.

![Video of running the interaction script and entering REST endpoints](https://user-images.githubusercontent.com/115161770/199294103-58f6bb76-7377-47de-b44a-1d13aed39f91.mp4)

Account `a` takes on the role of platform manager (i.e. the Alogrand Foundation) to create the platform 
(deployed App ID [119987642](https://testnet.algoexplorer.io/application/119987642) on Testnet) and set its parameters.
Since the platform was just created, it does not include any proposals yet.

![Video of user (a) creating the xGov platform](https://user-images.githubusercontent.com/115161770/199297648-38ecf14a-7f50-46b6-8477-02690e1d0b85.mp4)

Account `b` then connects to the platform.
Since it is connecting to the platform for the first time, an xGov escrow account is created for them.
The escrow is empty and not supporting any proposals. 

![Video of user (b) connecting to the xGov platform for the first time](https://user-images.githubusercontent.com/115161770/199297363-cbc242f6-662c-4cc4-9462-4a86881e2193.mp4)

Account `b` then creates a proposal (App ID 
[119988013](https://testnet.algoexplorer.io/application/119988013) on Testnet) on the xGov platform.
There are two options for how to create a proposal - either to type the text or enter a hash of the proposal.
In the former case, a hash of the entered text is calculated.
The hash `H` is stored in the created proposal smart contract together with the address of the proposer `P`.

![Video of user (b) creating a proposal](https://user-images.githubusercontent.com/115161770/199297727-37339db1-145e-4c7c-9742-e3d0bba1a4e1.mp4)

Even though account `b` created the proposal, it does not automatically start supporting it.
The user must do so explicitly (i.e. opt-in the escrow account into the created proposal).

![Video of user (b) starting to support the proposal](https://user-images.githubusercontent.com/115161770/199297781-e0135edc-5a8e-49c4-a523-15066a7875a0.mp4)

The user still has not assigned any stake to the support of the proposal.
To do this, one must first fund the escrow account.
This increases the available stake `AS` that can be committed to support any proposal on the platform.

![Video of user (b) funding the escrow account](https://user-images.githubusercontent.com/115161770/199297801-694b4496-9b6e-492c-9844-78cca3911ae9.mp4)

The user then selects what amount of the uncommitted stake will one assign to the support of the proposal.

![Video of user (b) assinging some funds to supporting the proposal
](https://user-images.githubusercontent.com/115161770/199297870-ebfec084-c6ef-499d-829d-048a6c9e3d36.mp4)

The user checks if his commitment is helping the proposal reach the commitment limit `CL`, 
i.e. if the time-weighted stake `WS` is increasing with each passing block.

*Note that the time-weighted stake is increasing with each block, but this is not reflected in the smart contract state 
until the contract is called since only then the state can be updated. The round number of the last update to the state
is stored in variable `LR`.*

![Video of user (b) calling the proposal smart contract to see how the time-weighted stake is increasing
](https://user-images.githubusercontent.com/115161770/199297877-a13abd78-e9ca-4293-b16c-24300345c545.mp4)

The user then decides to remove its stake from the proposal,
which is possible as long as the proposal has not reached the commitment limit, i.e. is put to the general vote.
The action clears the user's contribution towards the time-weighted commitment limit.

![Video of user (b) removing its commitment](https://user-images.githubusercontent.com/115161770/199297888-c810a8ba-f42e-4281-a798-13b7dc80f83a.mp4)

Account `c` then connects to the xGov.
Since it connects for the first time, an xGov escrow account is created also for them.

![Video of user (c) connecting to the xGov platform for the first time](https://user-images.githubusercontent.com/115161770/199297902-270866fb-bb7a-4e8a-bf83-c064994b9448.mp4)

The user decides to start supporting the proposal that was created by account `b`.
The number of accounts supporting the proposal `NS` increases back to `1`.

![Video of user (c) starting to support the proposal
](https://user-images.githubusercontent.com/115161770/199298051-2081985b-062f-4cdd-8efd-599cbbd7bc58.mp4)

The user `c` then funds their escrow and assigns a part of those funds to the support of the proposal.  

![Video of user (c) adding funds to their escrow and assigning a part of those to the support of the proposal
](https://user-images.githubusercontent.com/115161770/199298066-79c8d3f3-4349-47bf-a2af-1258a8c656fe.mp4)

Account `b` then connects to the xGov platform again.
Since it an escrow is already tied to their account, no escrow is created this time.

![Video of user (b) connecting to the xGov platform again](https://user-images.githubusercontent.com/115161770/199298081-d8ad8b6d-4ef8-403f-9466-ce4d4abc14da.mp4)

The user `b` then updates their proposal by entering a new text, which again gets stored in form of a hash in the 
proposal's smart contract.
Since the proposal has just been updated, the proposal becomes frozen `FR=1` (i.e. until the frozen duration `FD` 
passes).

![Video of user (b) updating the proposal](https://user-images.githubusercontent.com/115161770/199298117-eedb6398-4361-44ce-81f8-712e14153085.mp4)

While the proposal is frozen, the time-weighted stake `WS` is not getting updated (together with the last update round 
`LR`). Once enough rounds pass, the proposal becomes unfrozen `FR=0` and continues progressing towards the time-weighted
commitment.

![Video of proposal being frozen](https://user-images.githubusercontent.com/115161770/199298136-b79ed1be-f92c-4d98-8d4e-27bba64f8dcf.mp4)

User `b` then starts supporting the proposal again and committing some stake towards it.

![Video of user (b) starting to support the proposal again](https://user-images.githubusercontent.com/115161770/199298147-0b565c3e-4bf5-469b-9343-8254fb74b17b.mp4)

Account `a` connects again to the platform. It is recognized as the platform manager.

![Video of user (a) connecting to the xGov platform again](https://user-images.githubusercontent.com/115161770/199298172-435b904c-63b1-4905-a111-a67f286f511a.mp4)

The user `a` then keeps on checking if the proposal has already reached the commitment limit.

![Video of user (a) checking if the proposal has already reached the commitment limit
](https://user-images.githubusercontent.com/115161770/199298207-71bde7b2-30e7-4ccf-8f50-501814283558.mp4)

When the proposal reached the commitment limit, the user `a` tires to ratify the outcome as `passed`.
The action is denied because a locking duration (i.e. a cool down) has to pass before the outcome can be ratified as 
passed.

![Video of user (a) trying to ratify the outcome](https://user-images.githubusercontent.com/115161770/199298223-2cd96440-da54-4e59-b612-79391c559bac.mp4)

After the cool down end, the proposal is ratified as `passed`.
Both supporters receive a portion of the rewards based on their contributions towards the total time-weighted stake.
The proposal is then deleted from the platform.

![Video of user (a) ratifing the outcome](https://user-images.githubusercontent.com/115161770/199298240-871b6266-3977-4395-ad5f-284b7cedf81e.mp4)

Afterwards, account `b` logs into the platform again to withdraw some funds from their escrow.

![Video of user (b) withdrawing from escrow](https://user-images.githubusercontent.com/115161770/199298260-bfffdbec-09aa-44ef-b3d7-28f4d7d6407a.mp4)

The user `b` registers the remaining funds in the escrow for Algorand Governance.

![Video of user (b) registering for Algorand Governance](https://user-images.githubusercontent.com/115161770/199298275-a35f57e2-bc0d-4044-aa1a-e33a728827f7.mp4)

The user `b` then brings the escrow account online and again back offline.

![Video of user (b) bringing the escrow account online and back offline
](https://user-images.githubusercontent.com/115161770/199298293-4c55ada0-b7e9-4acc-bd95-06b5e686f194.mp4)

Finally, user `b` opts out of the xGov platform, closing their escrow.

![Video of user (b) opting out of xGov platform](https://user-images.githubusercontent.com/115161770/199298313-af03d20b-8d75-4b02-8f95-c08ccf364614.mp4)
