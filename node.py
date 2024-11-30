
import sys
import re
import json
import socket
import threading 
from threading import Lock
from datetime import datetime
import uuid
import tkinter as tk
import random
import time

# # Utility for formatted logging
# def log_message(message_type, details):
#     print(f"\n[{datetime.now().strftime('%H:%M:%S')}] {message_type}: {details}")


class Transaction:
    def __init__(self, txn_id=None, amount=None, sender=None, receiver=None, **kwargs):
        self.id = txn_id or str(uuid.uuid4())
        self.amount = amount
        self.sender = sender
        self.receiver = receiver
        self.timestamp = datetime.now().isoformat()
        

    def to_dict(self):
        return {
            "id": self.id,
            "amount": self.amount,
            "sender": self.sender,
            "receiver": self.receiver,
            "timestamp": self.timestamp,
        }


class Node:
    def __init__(self, nickname, address, log_callback=None):
        self.node_id = str(uuid.uuid4())
        self.nickname = nickname
        self.address = address
        self.balance = 1000.0
        self.peers = []
        self.transactions = {}
        self.running = True
        self.transaction_counter = 0
        self.lamport_clock = 0
        self.log_callback = log_callback
        self.failure_simulation = False  # Simulate failures (True to enable)
        self.drop_probability = 0.3     # 30% chance of dropping messages
        self.processed_transaction_ids = set()
        self.removed_peers = set()
        self.balances = {self.address: 1000.0}
        self.transaction_counter = 0  # Global counter for transaction IDs
        self.max_transaction_counter = 0  # Track the highest counter seen in the network
        self.removed_peers = set()  # Track removed peers
        self.peer_last_seen = {}  # Track last seen time for each peer
        threading.Thread(target=self.start_heartbeat, daemon=True).start()  # Start heartbeat
        self.counter_lock = Lock()  
        self.synchronize_balances()     # request balance of all known peers

        self.recent_discoveries = set()
        self.transaction_counter = len(self.transactions)
        
        # Validate IP Address
        host, port = self.address.split(":")
        try:
            socket.inet_aton(host)
        except socket.error:
            raise ValueError(f"Invalid IP address: {host}")

        # Create a UDP Socket
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_socket.bind((host, int(port)))
        self.log("Node Start", f"{self.nickname} listening on {self.address} (UDP)")

    def disconnect(self):
        self.log("Node Disconnection", "Simulating node disconnection.")
        self.running = False
        self.udp_socket.close()

    def reconnect(self):
        self.log("Node Reconnection", "Reconnecting the node.")
        self.running = True
        host, port = self.address.split(":")
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_socket.bind((host, int(port)))
        threading.Thread(target=self.listen, daemon=True).start()

    def increment_clock(self):
        self.lamport_clock += 1
        return self.lamport_clock
    
    def update_clock(self, incoming_timestamp):
        self.lamport_clock = max(self.lamport_clock, incoming_timestamp) + 1

    def log(self, log_type, message):
        if self.log_callback:
            self.log_callback(f"[{log_type}] {message}")
     
    def process_transaction(self, txn):

        # Check if the transaction has already been processed
        if txn.id in self.transactions: # ignore and skip
            return False, "Transaction already processed."

        # Validate sender's balance
        if txn.sender not in self.balances: # ignore and skip
            return False, f"Sender account '{txn.sender}' does not exist."

        if self.balances[txn.sender] < txn.amount:
            return False, "Insufficient funds."

        # Process the transaction: update balances
        self.balances[txn.sender] -= txn.amount
        self.balances[txn.receiver] = self.balances.get(txn.receiver, 0) + txn.amount

        # Add the transaction to local storage
        self.transactions[txn.id] = txn
        self.processed_transaction_ids.add(txn.id)

        # Log successful transaction processing
        self.log(
            "Transaction Processed",
            f"Transaction {txn.id}: {txn.sender} -> {txn.receiver} : {txn.amount:.2f}"
        )
        # Synchronize with peers after processing the transaction
        self.synchronize_transactions()

        return True, "Transaction processed successfully."

    def synchronize_balances(self):
     
        for peer in self.peers:
            self.request_balance(peer)


    def send_transaction(self, receiver_address, amount):
        # Prevent sending a transaction to self
        if receiver_address == self.address:
            self.log("Error", "Cannot send transaction to self.")
            return

        # Ensure the receiver is a valid peer
        if receiver_address not in self.peers:
            self.log("Error", f"Cannot send transaction: {receiver_address} is not a peer.")
            return

        # Ensure sufficient funds in the sender's account
        if self.address not in self.balances or self.balances[self.address] < amount:
            self.log("Error", "Insufficient balance in the specified account.")
            return

        # Create a unique transaction ID
        with self.counter_lock:
            txn_id = f"txn-{self.transaction_counter}"
            self.transaction_counter += 1

        # Increment the Lamport clock
        timestamp = self.increment_clock()

        # Create the transaction object
        txn = Transaction(
            txn_id=txn_id,
            amount=amount,
            sender=self.address,
            receiver=receiver_address,
            timestamp=timestamp,
        )

        # Deduct the amount from the sender's balance
        self.balances[self.address] -= amount
        self.transactions[txn.id] = txn

        # Log balance deduction on the sending node
        self.log("Balance Deducted", f"{self.address}: New Balance: {self.balances[self.address]}")

        # Broadcast the transaction
        if self.broadcast_transaction(txn):
            self.log("Transaction Sent", f"{self.address} -> {receiver_address}: {amount}")
            # Synchronize balances and transactions across the network
            self.synchronize_transactions()
        else:
            self.log("Error", f"Failed to send transaction to {receiver_address}")

    def broadcast_transaction(self, txn):
        if not self.peers:
            self.log("Warning", "No peers available to broadcast the transaction.")
            return False  # No peers to broadcast to

        success = False
        for peer in self.peers:
            try:
                self.send_udp_message("transaction", txn.to_dict(), peer)
                self.log("Broadcast", f"Transaction broadcasted to peer: {peer}")
                success = True
            except Exception as e:
                self.log("Error", f"Failed to broadcast transaction to {peer}: {e}")

        return success

    def send_ping(self, peer_address):
        # Validate the peer address format
        if not re.match(r"^\d{1,3}(\.\d{1,3}){3}:\d+$", peer_address):
            self.log("Error", f"Invalid peer address: {peer_address}. Format: IP:PORT")
            return

        # Add the peer to the sender's peer list
        self.add_peer(peer_address)

        # Send the ping message
        self.send_udp_message("ping", {"data": "Ping"}, peer_address)
        self.log("Ping", f"Ping sent to {peer_address}")

    def send_udp_message(self, message_type, data, peer_address, silent=False):
        """Send a UDP message to a peer."""
        # Simulate message drop
        if self.failure_simulation and random.random() < self.drop_probability:
            if not silent:
                self.log("Failure Simulation", f"Message to {peer_address} dropped.")
            return  # Simulate message drop

        if not re.match(r"^\d{1,3}(\.\d{1,3}){3}:\d+$", peer_address):
            if not silent:
                self.log("Error", f"Invalid peer address: {peer_address}. Format: IP:PORT")
            return

        message = {
            "message_id": str(uuid.uuid4()),
            "type": message_type,
            "data": data,
        }
        try:
            peer_host, peer_port = peer_address.split(":")
            self.udp_socket.sendto(json.dumps(message).encode("utf-8"), (peer_host, int(peer_port)))

            # Log only human-readable actions, not raw JSON
            if message_type == "balance_request":
                self.log("Requested Balance", f"Requested balance from {peer_address}")
        except Exception as e:
            if not silent:
                self.log("Error", f"Failed to send message to {peer_address}: {e}")

    def handle_udp_message(self, data, addr):
        try:
            # Decode and parse the incoming JSON message
            message = json.loads(data.decode("utf-8"))
            sender_address = f"{addr[0]}:{addr[1]}"
            message_type = message.get("type")

            # PING - PING-ACK
            if message_type == "ping":
            #    self.peer_last_seen[sender_address] = time.time()  # Update last seen time
                self.add_peer(sender_address)  # Ensure the peer is added
                self.send_udp_message("ping_ack", {"data": "Pong"}, sender_address)

            elif message_type == "ping_ack":
                self.peer_last_seen[sender_address] = time.time()  # Update last seen time
                self.add_peer(sender_address)  # Ensure the peer is added
                return  # Skip further processing

            # TRANSACTIONS
            if message_type == "transaction":
                txn_data = message.get("data", {})
                required_fields = ["id", "amount", "sender", "receiver", "timestamp"]
                
                # Validate that all required fields are present
                if not all(field in txn_data for field in required_fields):
                    self.log("Transaction Rejected", f"Missing required fields in transaction: {txn_data}")
                    return

                txn_id = txn_data.get("id")

                # Validate the transaction ID format
                if not re.match(r"^txn-\d+$", txn_id):
                    self.log("Transaction Rejected", f"Invalid transaction ID format: {txn_id}")
                    return

                # Validate transaction data
                try:
                    amount = float(txn_data.get("amount"))
                    if amount <= 0:
                        self.log("Transaction Rejected", f"Invalid transaction amount: {amount}")
                        return
                except ValueError:
                    self.log("Transaction Rejected", f"Amount is not a valid number: {txn_data.get('amount')}")
                    return

                # Create the transaction object
                txn = Transaction(**txn_data)

                # Process the transaction and log the outcome
                success, msg = self.process_transaction(txn)
                if success:
                    self.log("Transaction Processed", f"Transaction {txn.id}: {txn.sender} -> {txn.receiver} : {txn.amount:.2f}")
                else:
                    self.log("Transaction Failed", f"Transaction {txn.id}: {msg}")

           

            elif message_type == "transaction_request":
                txn_id = message.get("data", {}).get("transaction_id")
                if txn_id and txn_id in self.transactions:
                    txn = self.transactions[txn_id]
                    self.send_udp_message(
                        "transaction_response",
                        txn.to_dict(),
                        sender_address,
                    )
                    self.log("Transaction Response Sent", f"Sent transaction {txn_id} to {sender_address}")

            elif message_type == "transaction_response":
                txn_data = message.get("data", {})
                txn_id = txn_data.get("id")

                # Validate the received transaction data
                if not txn_id or not all(key in txn_data for key in ["id", "amount", "sender", "receiver", "timestamp"]):
                    self.log("Error", f"Invalid or incomplete transaction data received from {sender_address}: {txn_data}")
                    return

                # Check if the transaction already exists
                if txn_id in self.transactions:
                    self.log("Transaction Duplicate", f"Transaction {txn_id} already exists. Ignoring response.")
                    return

                # Add the transaction to the local store
                txn = Transaction(**txn_data)
                self.transactions[txn.id] = txn
                self.log("Transaction Added", f"Transaction {txn.id} added to local store from {sender_address}")

                # Check if there are any unresolved requests for this transaction
                if txn_id in self.processed_transaction_ids:
                    self.processed_transaction_ids.remove(txn_id)  # Mark as resolved
                    self.log("Transaction Resolved", f"Resolved transaction request for {txn_id}.")

                if self.log_callback and callable(getattr(self, "handle_transaction_response", None)):
                    self.log_callback(f"Received transaction: {txn.to_dict()}")

            # SYNC Messages
            elif message_type == "full_sync_request":
                    sync_data = {
                        "balances": self.balances,
                        "transactions": self.get_all_transactions(),
                        "peers": self.peers,
                    }
                    self.send_udp_message("full_sync_response", sync_data, sender_address)
                    self.log("Full Sync Response Sent", f"Sent full sync data to {sender_address}")

            elif message_type == "full_sync_response":
                data = message.get("data", {})
                self.merge_balances(data.get("balances", {}))
                self.merge_transactions(data.get("transactions", []))
                self.merge_peers(data.get("peers", []))
                self.log("Rebuild Complete", "Node state rebuilt successfully from the network.")
                self.log("Balances", f"Updated Balances: {self.balances}")
                self.log("Peers", f"Updated Peers: {self.peers}")

            # DETAIL/DISCOVERY MESSAGES
            elif message_type == "details_request":
                self.send_node_details(sender_address)

            elif message_type == "discovery_request":
                self.handle_discovery_request(sender_address)

            elif message_type == "discovery_response":
                self.merge_peers(message.get("data", {}).get("peers", []))
                self.log("Discovery", f"Updated peer list from {sender_address}")


            # BALANCE 
            elif message_type == "balance_response":
                balance_data = message.get("data", {})
                address = balance_data.get("address")
                balance = balance_data.get("balance")
                if address and balance is not None:
                    # Update the balances dictionary
                    self.balances[address] = balance  # Add or update the peer's balance
                    self.log("Balance Received", f"{address} has a balance of {balance:.2f}")
                else:
                    self.log("Error", f"Invalid balance data received from {sender_address}")

            elif message_type == "balance_request":
                # Respond to the balance request
                balance_data = {
                    "address": self.address,
                    "balance": self.balances.get(self.address, 0.0),
                }
                self.send_udp_message("balance_response", balance_data, sender_address)
                self.log("Balance Response Sent", f"Sent balance to {sender_address}")

            # SYNC 
            elif message_type == "sync_request":
                sync_data = {
                    "balances": self.balances,
                    "transactions": self.get_all_transactions(),
                    "peers": self.peers,
                }
                self.send_udp_message("sync_response", sync_data, sender_address)
                self.log("Sync Response", f"Sent sync response to {sender_address}")

            elif message_type == "sync_response":
                data = message.get("data", {})
                peer_counter = data.get("transaction_counter", 0)
                peer_transactions = data.get("transactions", [])
                peer_balances = data.get("balances", {})
                peer_hash = data.get("transaction_hash")  # Hash of transactions from the peer

                # Update max transaction counter
                self.max_transaction_counter = max(self.max_transaction_counter, peer_counter)
                self.transaction_counter = max(self.transaction_counter, self.max_transaction_counter + 1)

                self.merge_balances(peer_balances)
                # Compare transaction hashes for consistency
                local_hash = self.calculate_transaction_hash()

                if peer_hash and peer_hash != local_hash:
                    self.log("Sync Mismatch", f"Transaction hash mismatch with peer {sender_address}. Resolving...")
                    self.merge_transactions(peer_transactions)
                    updated_hash = self.calculate_transaction_hash()

                    if updated_hash == peer_hash:
                        self.log("Sync Resolved", f"Transactions synchronized successfully with {sender_address}.")
                    else:
                        self.log("Sync Incomplete", f"Hash mismatch persists after merging with {sender_address}.")
                else:
                    self.log("Sync Complete", f"Transaction hashes match with {sender_address}. No further action required.")

                # Merge peers to ensure consistent network state
                self.merge_balances(peer_balances)

        except json.JSONDecodeError as e:
            self.log("Error", f"Invalid JSON data received from {addr}: {data}, error: {e}")

        except Exception as e:
            self.log("Error", f"Handling message from {addr}: {e}")


    def get_all_transactions(self):
        return [txn.to_dict() for txn in self.transactions.values()]


    def merge_transactions(self, peer_transactions):
        """Merge transactions from peers, avoiding duplicates and validating IDs."""
        for txn_data in peer_transactions:
            txn_id = txn_data.get("id")

            # Ensure the transaction ID follows the format `txn-<index>`
            if not re.match(r"^txn-\d+$", txn_id):
                self.log("Transaction Rejected", f"Invalid transaction ID format: {txn_id}")
                continue

            try:
                txn_index = int(txn_id.split("-")[1])
            except ValueError:
                self.log("Transaction Rejected", f"Invalid transaction ID format: {txn_id}")
                continue

            # Avoid duplicates
            if txn_id in self.transactions:
                continue
            
            # Add the transaction
            txn = Transaction(**txn_data)
            self.transactions[txn.id] = txn
            self.log("Transaction Added", f"ID: {txn.id}, Sender: {txn.sender}, Receiver: {txn.receiver}, Amount: {txn.amount}")
            
            # Update the global counter
       #     self.max_transaction_counter = max(self.max_transaction_counter, txn_counter)
            self.transaction_counter = max(self.transaction_counter, self.max_transaction_counter + 1)



    def merge_peers(self, incoming_peers):
        """Merge a list of incoming peers, avoiding duplicates and redundant updates."""
        for peer in incoming_peers:
            if peer != self.address and peer not in self.peers:
                self.peers.append(peer)
                self.peer_last_seen[peer] = time.time()  # Track last seen time
                self.log("Peer Added", f"Added peer {peer}")
                
                # Request balance from the new peer
                self.send_udp_message("balance_request", {}, peer)

    def merge_balances(self, incoming_balances):
        for account, balance in incoming_balances.items():
            if account in self.balances:
                # Update balance to the latest value from peers
                self.balances[account] = max(self.balances[account], balance)
            else:
                self.balances[account] = balance
        self.log("Balances Merged", f"Updated Balances: {self.balances}")

    def add_peer(self, peer_address):
        """Add a peer to the node's peer list if valid, not self, not a duplicate, and not removed."""
        # Validate the peer address format
        if not re.match(r"^\d{1,3}(\.\d{1,3}){3}:\d+$", peer_address):
            self.log("Peer Rejected", f"Invalid peer address format: {peer_address}")
            return

        # Prevent adding self
        if peer_address == self.address:
            self.log("Peer Rejected", f"Cannot add self as a peer: {peer_address}")
            return

        # Prevent adding duplicates
        if peer_address in self.peers:
           
            return

        # Prevent adding previously removed peers
        if peer_address in self.removed_peers:
            self.log("Peer Rejected", f"{peer_address} was previously removed. Ignoring.")
            return

        # Add the peer
        self.peers.append(peer_address)
        self.peer_last_seen[peer_address] = time.time()  # Track last seen time

        # Initialize the balance if it doesn't exist
        if peer_address not in self.balances:
            self.balances[peer_address] = 1000  # Default balance initialization

        self.log("Peer Added", f"{peer_address} added successfully.")
        # Notify existing peers about the updated peer list
        self.notify_peers_about_update()
        # Request balance from the added peer
        self.request_balance(peer_address)
        self.send_udp_message("balance_request", {}, peer_address)


    def notify_peers_about_update(self):
        """Notify all peers about the updated peer list."""
        for peer in self.peers:
            try:
                self.send_udp_message("discovery_response", {"peers": self.peers}, peer)
                self.log("Peer Notification", f"Notified {peer} about updated peer list.")
            except Exception as e:
                self.log("Error", f"Failed to notify peer {peer} about updated peer list: {e}")


    def remove_peer(self, peer_address):
        """Remove a peer from the network and stop the node if necessary."""

        if peer_address in self.peers:
            self.peers.remove(peer_address)
            self.removed_peers.add(peer_address)  # Mark the peer as removed
            self.log("Peer Removed", f"{peer_address} removed from peers.")
            # Notify remaining peers about the updated peer list
            for peer in self.peers:
                self.send_udp_message("discovery_response", {"peers": self.peers}, peer)

            # Stop the peer node if it's the current node
            if peer_address == self.address:
                self.log("Node Stopping", f"Node {peer_address} is stopping.")
                self.stop()

        else:
            self.log("Peer Not Found", f"Peer {peer_address} is not in the peer list.")



    def send_node_details(self, peer_address):
        """Send node details, including formatted transactions, to a peer."""
        formatted_transactions = [
            {
                "Id": txn.id,
                "Sender": txn.sender,
                "Receiver": txn.receiver,
                "Amount": txn.amount,
                "Time": txn.timestamp,
            }
            for txn in self.transactions.values()
        ]
        details = {
            "nickname": self.nickname,
            "address": self.address,
            "balances": self.balances,
            "peers": self.peers,
            "transactions": formatted_transactions,
        }
        self.send_udp_message("details_response", details, peer_address)

    def get_node_details(self):
        # Create the main details window
        details_window = tk.Toplevel(self.master)
        details_window.title("Node Details")

        # Display node name and address
        tk.Label(details_window, text=f"Node Name: {self.nickname}", font=("Arial", 14)).pack(pady=5)
        tk.Label(details_window, text=f"Address: {self.address}", font=("Arial", 12)).pack(pady=5)

        # Display current node balance
        balance_frame = tk.LabelFrame(details_window, text="Current Node Balance")
        balance_frame.pack(fill="both", expand=True, padx=10, pady=5)
        tk.Label(balance_frame, text=f"Balance: {self.balances.get(self.address, 0.0):.2f}", font=("Arial", 12)).pack(pady=5)

        # Display connected peers and their balances
        peers_frame = tk.LabelFrame(details_window, text="Connected Peers and Balances")
        peers_frame.pack(fill="both", expand=True, padx=10, pady=5)

        # Headers for peers and balances
        tk.Label(peers_frame, text="Peer Address", font=("Arial", 10, "bold")).grid(row=0, column=0, padx=10, pady=5)
        tk.Label(peers_frame, text="Balance", font=("Arial", 10, "bold")).grid(row=0, column=1, padx=10, pady=5)

        # Populate peers and balances
        for idx, peer in enumerate(self.peers, start=1):
            balance = self.balances.get(peer, "Unknown")
            tk.Label(peers_frame, text=peer, font=("Arial", 10)).grid(row=idx, column=0, padx=10, pady=5, sticky="w")
            tk.Label(peers_frame, text=f"{balance:.2f}" if isinstance(balance, (float, int)) else balance, font=("Arial", 10)).grid(row=idx, column=1, padx=10, pady=5, sticky="e")

        # Display transactions
        transaction_frame = tk.LabelFrame(details_window, text="Transactions")
        transaction_frame.pack(fill="both", expand=True, padx=10, pady=5)

        if self.transactions:
            transactions = [
                f"{txn.sender} -> {txn.receiver} : {txn.amount:.2f} at {txn.timestamp}"
                for txn in self.transactions.values()
            ]
            for idx, txn in enumerate(transactions, start=1):
                tk.Label(transaction_frame, text=txn, font=("Arial", 10)).pack(anchor="w", padx=10, pady=2)
        else:
            tk.Label(transaction_frame, text="No transactions recorded.", font=("Arial", 10)).pack(pady=10)

        # Close button
        tk.Button(details_window, text="Close", command=details_window.destroy).pack(pady=10)


    def format_transactions(self):
        if not self.transactions:
            return "No transactions found."
        return "\n".join([
            f"Id: {txn.id}\n"
            f"Sender: {txn.sender}\n"
            f"Receiver: {txn.receiver}\n"
            f"Amount: {txn.amount}\n"
            f"Time: {txn.timestamp}\n"
            "-----------------------------------"
            for txn in self.transactions.values()
        ])

    def handle_discovery_request(self, sender_address):
        if sender_address in self.recent_discoveries:
            return
        if sender_address in self.removed_peers:
            return  # Ignore requests from removed peers

        self.recent_discoveries.add(sender_address)
        if len(self.recent_discoveries) > 100:  # Limit cache size
            self.recent_discoveries.pop()

        self.peer_last_seen[sender_address] = time.time()
        self.add_peer(sender_address)
        # Request balance from the discovered peer
        self.request_balance(sender_address)

        # Send discovery response
        MAX_PEERS_TO_SEND = 50
        peers_subset = [peer for peer in self.peers if peer != sender_address][:MAX_PEERS_TO_SEND]
        self.send_udp_message("discovery_response", {"peers": peers_subset}, sender_address)
        self.log("Discovery", f"Exchanged peer list with {sender_address}")


    def handle_balance_response(self, data, sender_address):
        balance = data.get("balance")
        if balance is not None:
            self.log("Balance Received", f"{sender_address} has balance {balance}")
        else:
            self.log("Error", f"Invalid balance data received from {sender_address}")


    def request_discovery(self, port_range=(5001, 5010)):
        """
        Discover peers on the specified IP address within a range of ports.
        :param port_range: Tuple of (start_port, end_port) to scan for peers.
        """
        start_port, end_port = port_range
        ip = self.address.split(":")[0]  # Extract IP from the node's address
        self.log("Discovery", f"Starting discovery on IP {ip} in port range {start_port}-{end_port}.")

        for port in range(start_port, end_port + 1):
            peer_address = f"{ip}:{port}"

            # Skip if the peer is already in the list or is the current node itself
            if peer_address in self.peers or peer_address == self.address:
                continue

            # Send discovery request
            self.send_udp_message("discovery_request", {}, peer_address)
            self.log("Discovery Request Sent", f"Sent discovery request to {peer_address}")


    def synchronize_transactions(self):
        if not self.peers:
            self.log("Sync", "No peers available for synchronization.")
            return
        # Send sync request to all peers
        for peer in self.peers:
            sync_data = {
                "transactions": self.get_all_transactions(),
                "transaction_counter": self.transaction_counter,
            }
            self.send_udp_message("sync_request", sync_data, peer)
            self.log("Sync Request Sent", f"Sent sync request to {peer}")

    def list_transactions(self):
        """Log all transactions in the formatted style."""
        transactions = self.format_transactions()
        if not self.transactions:
            self.log("Transactions", "No transactions found.")
        else:
            self.log("Transactions", transactions)

    def request_balance(self, peer_address):
        """Request balance from a peer."""
        if not re.match(r"^\d{1,3}(\.\d{1,3}){3}:\d+:\d+$", peer_address):
            return

        # Log the balance request in a human-readable format
        self.log("Request Balance", f"Requesting balance from {peer_address}")
        
        # Send the balance request without logging raw JSON
        self.send_udp_message("balance_request", {}, peer_address, silent=True)


    def calculate_transaction_hash(self):
        """Calculate a simple hash for the current transaction list."""
        txn_data = "".join(sorted(txn.id for txn in self.transactions.values()))
        return hash(txn_data)

    def synchronize_transactions(self):
        """Synchronize transactions with peers and check consistency."""
        if not self.peers:
            self.log("Sync", "No peers available for synchronization.")
            return

        local_hash = self.calculate_transaction_hash()
        for peer in self.peers:
            sync_data = {
                "transaction_hash": local_hash,
                "transactions": self.get_all_transactions(),
                "transaction_counter": self.transaction_counter,
            }
            self.send_udp_message("sync_request", sync_data, peer)
            self.log("Sync Request Sent", f"Sent sync request to {peer}")

    def get_transaction_by_index(self, index):
        try:
            # Convert the transactions dictionary to a list of transactions
            transactions_list = list(self.transactions.values())
            
            # Retrieve the transaction at the specified index
            if index < 0 or index >= len(transactions_list):
                return {"error": f"Index {index} out of range. Available transactions: {len(transactions_list)}"}

            transaction = transactions_list[index]
            return transaction.to_dict()
        except Exception as e:
            return {"error": f"An error occurred while retrieving the transaction: {e}"}


    def join_network(self, peer_address):
        """Join a network by connecting to a known peer."""
        if peer_address in self.peers:
            return

        self.log("Join Network", f"Connecting to {peer_address}")
   
        self.add_peer(peer_address)

        # Request discovery from the new peer
        self.send_udp_message("discovery_request", {}, peer_address)

        # Synchronize transactions and balances after discovery
        self.log("Join Network", f"Requesting synchronization from {peer_address}")
        self.send_udp_message("sync_request", {}, peer_address)

    def listen(self):
        while self.running:
            try:
                data, addr = self.udp_socket.recvfrom(1024)
                threading.Thread(target=self.handle_udp_message, args=(data, addr), daemon=True).start()
            except OSError:
                if not self.running:
                    self.log("Node", "Node stopped listening as requested.")
                else:
                    self.log("Error", "Unexpected socket error while listening.")
            except Exception as e:
                self.log("Error", f"Unhandled error in listening loop: {e}")

    def start_heartbeat(self, interval=5, timeout=15):
        """Start a periodic heartbeat to check the status of peers."""
        self.heartbeat_lock = Lock()
        self.peer_last_seen = {peer: time.time() for peer in self.peers}

        def heartbeat():
            while self.running:
                with self.heartbeat_lock:
                    current_time = time.time()
                    for peer in self.peers.copy():
                        if current_time - self.peer_last_seen.get(peer, 0) > timeout:
                            self.log("Peer Timeout", f"Peer {peer} did not respond in {timeout} seconds. Removing.")
                            self.peers.remove(peer)
                            self.notify_peers_about_update()

                        self.send_udp_message("ping", {"data": "Heartbeat check"}, peer, silent=True)

                time.sleep(interval)

        threading.Thread(target=heartbeat, daemon=True).start()

    def clear_and_rebuild_data(self):
        # Confirm with the user before proceeding
        confirm = tk.messagebox.askyesno(
            "Clear and Rebuild Data",
            "Are you sure you want to clear all local data? This will prevent rejoining the network."
        )
        if not confirm:
            return

        # Log the start of the process
        self.log("Data Management", "Clearing local transactions, balances, and peers.")

        # Backup the current list of peers (optional for debugging/logging purposes)
        current_peers = self.peers.copy()

        # Clear local state
        self.transactions.clear()
        self.balances = {self.address: 1000.0}  # Reset balance for the node's address
        self.peers = []  # Clear peer list
        self.removed_peers.update(current_peers)  # Mark all current peers as removed

        # Log the state after clearing
        self.log("Data Management", "Local state cleared. Preventing rejoining of peers.")

        # Check if there are any peers to rebuild data from
        if not current_peers:
            self.log("Data Management", "No peers available for rebuilding. Local state cleared.")
            return

        # Log rebuild initiation (Optional: Skip rebuild altogether)
        self.log("Data Management", f"Rebuild process skipped. Current state: Transactions={len(self.transactions)}, Balances={self.balances}, Peers={self.peers}.")


    def clear_local_data(self):
        """Clear all local data including transactions, balances, and peers."""
        self.log("Data Management", "Clearing all local data...")
        self.transactions.clear()
        self.balances = {self.address: 1000.0}  # Reset the balance for the node itself
        self.peers.clear()

    
    def rebuild_from_network(self):
        """Prevent rebuilding peers during a cleared state."""
        self.log("Data Management", "Rebuild skipped to prevent automatic rejoining of peers.")

    def stop(self):
        self.running = False
        with self.heartbeat_lock:
            pass  # Allow any ongoing heartbeat operations to finish
        try:
            self.udp_socket.close()
            self.log("Node", "Node stopped gracefully.")
        except Exception as e:
            self.log("Error", f"Failed to close socket: {e}")



if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python node.py <port> [<ip>]")
        sys.exit(1)

    port = int(sys.argv[1])
    ip = sys.argv[2] if len(sys.argv) > 2 else "0.0.0.0"