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
import os

class Transaction:
    def __init__(self, txn_id=None, amount=None, sender=None, receiver=None, file_path = None, **custom_fields):
        self.id = txn_id or str(uuid.uuid4())
        self.amount = amount
        self.sender = sender
        self.receiver = receiver
        self.timestamp = datetime.now().isoformat()
        self.custom_fields = custom_fields
        self.file_path = file_path  # New field for binary file path

    def to_dict(self):
        base_dict = {
            "id": self.id,
            "amount": self.amount,
            "sender": self.sender,
            "receiver": self.receiver,
            "file_path": self.file_path,  
            "timestamp": self.timestamp,
        }
        return {**base_dict, "custom_fields": self.custom_fields}

    @classmethod
    def from_dict(cls, data):
        # Separate custom fields from the required fields
        required_fields = {"id", "amount", "sender", "receiver", "timestamp", "file_path"}
        base_data = {key: data[key] for key in required_fields if key in data}
        custom_data = data.get("custom_fields", {})
        return cls(**base_data, **custom_data)

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
        self.awaited_responses = {}  # To store awaited responses
        self.response_lock = Lock()  # To synchronize access
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

        # allow a sync to occur after each transaction occurs to ensure peer nodes note the change
    def auto_sync_with_delay(self, delay=5):
        def sync_task():
            time.sleep(delay)
            self.synchronize_transactions()
            self.log("Auto-sync", "Synchronized transactions with peers after delay.")

        # Run the sync task in a separate thread to avoid blocking the GUI
        threading.Thread(target=sync_task, daemon=True).start()

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
        if txn.id in self.processed_transaction_ids or txn.id in self.processed_transaction_ids:
            self.log("Duplicate Broadcast", f"Transaction {txn.id} already broadcasted.")
            return False

        # Validate sender's balance
        if txn.sender not in self.balances: # ignore and skip
            return False, f"Sender account '{txn.sender}' does not exist."

        if self.balances[txn.sender] < txn.amount:
            return False, "Insufficient funds."

        # Process the transaction: update balances
        with self.counter_lock:
            self.balances[txn.sender] -= txn.amount
            if txn.receiver not in self.balances:
                self.log("New Account", f"Created new account for receiver: {txn.receiver}")
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
        self.synchronize_balances()

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
        # Broadcast the transaction
        if self.broadcast_transaction(txn):
            # Deduct the amount from the sender's balance after successful broadcast
            self.balances[self.address] -= amount
            self.transactions[txn.id] = txn
            self.log("Transaction Sent", f"{self.address} -> {receiver_address}: {amount}")
            self.log("Balance Deducted", f"{self.address}: New Balance: {self.balances[self.address]}")
        else:
            self.log("Error", f"Failed to send transaction to {receiver_address}")
        # Auto-sync after a delay
        self.auto_sync_with_delay()


    def send_custom_transaction(self, receiver_address, amount, **custom_fields):
        if receiver_address == self.address:
            self.log("Error", "Cannot send transaction to self.")
            return
        if receiver_address not in self.peers:
            self.log("Error", f"Cannot send transaction: {receiver_address} is not a peer.")
            return

        if self.address not in self.balances or self.balances[self.address] < amount:
            self.log("Error", "Insufficient balance.")
            return
        # Validate custom fields to ensure no conflicts
        reserved_fields = {"id", "amount", "sender", "receiver", "timestamp"}
        invalid_keys = reserved_fields.intersection(custom_fields.keys())
        if invalid_keys:
            self.log("Error", f"Custom fields contain reserved keys: {invalid_keys}")
            return
        # Create a unique transaction ID
        with self.counter_lock:
            txn_id = f"custom-{self.transaction_counter}"
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
            **custom_fields  # Pass custom fields here
        )
        # Broadcast the transaction
        if self.broadcast_transaction(txn):
            # Deduct the amount from the sender's balance after successful broadcast
            self.balances[self.address] -= amount
            self.transactions[txn.id] = txn
            self.log("Custom Transaction Sent", f"{txn.id} -> {receiver_address}: {amount}, Custom: {custom_fields}")
            self.log("Balance Deducted", f"{self.address}: New Balance: {self.balances[self.address]}")
        else:
            self.log("Broadcast Failed", f"Failed to broadcast {txn.id}")
        # Auto-sync after a delay
        self.auto_sync_with_delay()

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

    def send_udp_message(self, message_type, data, peer_address, silent=True):
        try:
            # Validate peer address format
            if not re.match(r"^\d{1,3}(\.\d{1,3}){3}:\d+$", peer_address):
                if not silent:
                    self.log("Error", f"Invalid peer address: {peer_address}. Expected format: IP:PORT")
                return

            # Prepare the message
            message = {
                "message_id": str(uuid.uuid4()),  # Unique ID for tracking messages
                "type": message_type,
                "data": data
            }

            # Extract the peer's host and port
            peer_host, peer_port = peer_address.split(":")
            peer_port = int(peer_port)
            # Serialize the message to JSON and send it
            self.udp_socket.sendto(json.dumps(message).encode("utf-8"), (peer_host, peer_port))

            # Log the action if silent mode is not enabled
            if not silent:
                self.log("UDP Message Sent", f"Sent {message_type} to {peer_address} with data: {data}")

        except json.JSONDecodeError as e:
            # Log JSON encoding errors
            if not silent:
                self.log("Error", f"Failed to encode message to JSON: {e}")

        except ValueError as e:
            # Log value errors, like invalid port number
            if not silent:
                self.log("Error", f"Invalid peer address or data: {peer_address}, error: {e}")

        except Exception as e:
            # Log any other exceptions
            if not silent:
                self.log("Error", f"Failed to send {message_type} to {peer_address}: {e}")

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

            # File Send Request
            if message_type == "file_transfer_request":
                file_metadata = message.get("data", {}).get("metadata")
                if not file_metadata or not file_metadata.get("file_name"):
                    return

                self.log("File Transfer", f"Received file transfer request from {sender_address} with metadata: {file_metadata}")

                # Initialize variables for port selection
                max_retries = 5  # Maximum number of retries to find a free port
                listen_port = None

                for _ in range(max_retries):
                    try:
                        proposed_port = random.randint(5000, 6000)  # Choose a random port
                        # Test if the port is available
                        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as test_socket:
                            test_socket.bind(("0.0.0.0", proposed_port))  # Bind the proposed port
                            listen_port = proposed_port  # Mark this port as usable
                            break  # Exit loop if port is successfully bound
                    except OSError:
                        self.log("Error", f"Port {proposed_port} is unavailable. Retrying...")

                if listen_port is None:
                    self.log("Error", "Failed to find a free port for file transfer after multiple attempts.")
                    return

                # Start listening for the file on the chosen port
                threading.Thread(target=self.receive_file, args=(listen_port,), daemon=True).start()

                # Respond with the chosen port for the file transfer
                self.send_udp_message(
                    "file_transfer_port_response",
                    {"port": listen_port, "metadata": file_metadata},
                    sender_address
                )
                self.log("File Transfer", f"Responded with file transfer port {listen_port} to {sender_address}")
           
            # File Accept (Start Sending File)
            elif message_type == "file_accept":
                file_name = message.get("data", {}).get("file_name")
                if file_name:
                    self.log("File Transfer", f"{sender_address} accepted the file transfer for '{file_name}'")
                    threading.Thread(target=self.send_file, args=(file_name, sender_address), daemon=True).start()

            # Handle file transfer port response
            elif message_type == "file_transfer_port_response":
                response_data = message.get("data", {})
                peer_port = response_data.get("port")
                file_metadata = response_data.get("metadata")
                self.log("File Transfer", f"Received file metadata: {file_metadata}")

                if not response_data:
                    return
                if not peer_port:
                    return

                self.log(
                    "File Transfer",
                    f"Received file transfer port {peer_port} from {sender_address} with metadata {file_metadata}"
                )

                # Proceed to send the file using the provided port
                if peer_port:
                    file_path = file_metadata.get("file_path")  # Ensure file path is known
                    if file_path:
                        self.send_file(file_path, f"{addr[0]}:{peer_port}")
                   

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
                if not re.match(r"^(txn|custom)-\d+$", txn_id):
                    self.log("Transaction Rejected", f"Invalid transaction ID format: {txn_id}")
                    return
                
                try:
                    txn = Transaction.from_dict(txn_data)
                    success, msg = self.process_transaction(txn)
                    if success:
                        self.log("Transaction Processed", f"Transaction {txn.id}: {txn.sender} -> {txn.receiver}")
                    else:
                        self.log("Transaction Failed", msg)
                except Exception as e:
                    self.log("Transaction Error", f"Error processing transaction: {e}")

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
            self.transaction_counter = max(self.transaction_counter, self.max_transaction_counter + 1)
             # Refresh the GUI after merging
            self.list_transactions()

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


    def request_discovery(self, peer_ips):
        """
        Sends a discovery request to the specified peer IPs.
        :param peer_ips: List of peer IPs or IP:PORT combinations.
        """
        for ip in peer_ips:
            try:
                # Split IP and port if provided, or use default port
                if ":" in ip:
                    host, port = ip.split(":")
                    port = int(port)
                else:
                    host = ip
                    port = 5001  # Default port if not specified

                # Validate the IP address format
                try:
                    socket.inet_aton(host)  # Validate host
                except socket.error:
                    raise ValueError(f"Invalid IP address: {host}")

                peer_address = f"{host}:{port}"

                # Skip if the peer is already connected or is the current node itself
                if peer_address in self.peers or peer_address == self.address:
                    self.log("Discovery Skipped", f"Peer {peer_address} is already connected or is self.")
                    continue

                # Send a discovery request to the peer
                self.send_udp_message("discovery_request", {}, peer_address)
                self.log("Discovery Request Sent", f"Sent discovery request to {peer_address}")

            except Exception as e:
                self.log("Discovery Error", f"Error discovering peer {ip}: {e}")

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

    def send_file(self, file_path, peer_address, max_retries=3):
        """Send a file to a peer via TCP with multiple retry attempts."""
        try:
            if not os.path.exists(file_path):
                self.log("Error", f"File {file_path} does not exist.")
                return

            # Read file data
            with open(file_path, "rb") as file:
                file_data = file.read()

            # Extract file metadata
            file_metadata = {
                "file_name": os.path.basename(file_path),
                "file_size": os.path.getsize(file_path),
            }

            for attempt in range(1, max_retries + 1):
                try:
                    # Send a file transfer request to the peer
                    self.send_udp_message("file_transfer_request", {"metadata": file_metadata}, peer_address)
                    self.log("File Transfer", f"Attempt {attempt}: Requesting file transfer to {peer_address}")

                    # Wait for a response with the port for file transfer
                    response = self.await_response("file_transfer_port_response", peer_address)
                    if not response or "port" not in response:
                        raise ValueError(f"Invalid or missing port in response: {response}")

                    # Retrieve the port and establish a direct connection
                    peer_port = response["port"]
                    peer_host, _ = peer_address.split(":")
                    
                    for tcp_attempt in range(1, max_retries + 1):
                        try:
                            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp_socket:
                                self.log("TCP Connection", f"Attempt {tcp_attempt}: Connecting to {peer_host}:{peer_port}")
                                tcp_socket.connect((peer_host, peer_port))
                                tcp_socket.sendall(file_data)
                            self.log("File Sent", f"File {file_path} successfully sent to {peer_address}")
                            return  # Exit if successful
                        except Exception as tcp_error:
                            self.log("Error", f"Attempt {tcp_attempt}: TCP connection failed: {tcp_error}")
                            if tcp_attempt == max_retries:
                                raise

                except Exception as udp_error:
                    self.log("Error", f"Attempt {attempt}: Failed to get response from {peer_address}: {udp_error}")
                    if attempt == max_retries:
                        raise

        except Exception as e:
            self.log("Error", f"Failed to send file {file_path} to {peer_address}: {e}")


    def send_file_request(self, file_path, receiver_address):
        """Send a file transfer request to a peer."""
        if not os.path.exists(file_path):
            self.log("Error", f"File {file_path} does not exist.")
            return

        # Extract file metadata
        file_metadata = {
            "file_path": file_path,
            "file_name": os.path.basename(file_path),
            "file_size": os.path.getsize(file_path),
        }
        self.send_udp_message("file_transfer_request", {"metadata": file_metadata}, receiver_address)

        self.log("File Transfer", f"Requesting file transfer to {receiver_address} with metadata {file_metadata}")

    def handle_file_reception(self, client_socket, addr):
        """Receive a file sent by a peer and save it locally."""
        try:
            file_data = b""  # Initialize an empty bytes object to store the received data
            while chunk := client_socket.recv(4096):  # Receive data in chunks of 4096 bytes
                file_data += chunk
            
            # Save the received data to a file
            file_path = f"received_file_{uuid.uuid4().hex}.dat"  # Save with a unique name
            with open(file_path, "wb") as file:
                file.write(file_data)
            
            self.log("File Received", f"File received from {addr} and saved as {file_path}")
        except Exception as e:
            self.log("Error", f"Failed to receive file from {addr}: {e}")
        finally:
            client_socket.close()  # Close the client connection

    def await_response(self, expected_type, peer_address, timeout=10):
        """Wait for a specific type of response from a specific peer."""
        self.udp_socket.settimeout(timeout)  # Set the timeout for the socket
        try:
            start_time = time.time()  # Record the start time
            while time.time() - start_time < timeout:
                data, addr = self.udp_socket.recvfrom(4096)  # Receive data from the socket
                # Convert addr tuple to string format (e.g., "192.168.0.32:5003")
                sender_address = f"{addr[0]}:{addr[1]}"
                # Check if the sender matches the expected peer
                if sender_address == peer_address:
                    message = json.loads(data.decode("utf-8"))  # Decode JSON message
                    if message.get("type") == expected_type:  # Check message type
                        return message.get("data")  # Return the data if type matches
        except socket.timeout:
            self.log("Error", f"Timeout waiting for {expected_type} from {peer_address}")  # Handle timeout
        except Exception as e:
            self.log("Error", f"Unexpected error while waiting for {expected_type} from {peer_address}: {e}")
        return None  # Return None if no matching response is received



    def broadcast_udp_message(self, message_type, data):
        """Broadcast a UDP message to all connected peers."""
        for peer in self.peers:
            self.send_udp_message(message_type, data, peer)

    def join_network(self, peer_address):
        """Join a network by connecting to a known peer."""
        if peer_address in self.peers:
            return

        self.log("Join Network", f"Connecting to {peer_address}")
        self.add_peer(peer_address)

        # Request discovery from the new peer
        self.send_udp_message("discovery_request", {}, peer_address)
        # Synchronize transactions and balances after discovery
      
        self.send_udp_message("sync_request", {}, peer_address)
        self.send_udp_message("full_sync_request", {}, peer_address)
        self.log("Join Network", f"Requesting synchronization from {peer_address}")

    def send_file_to_peer(self, file_path, peer_address):
        """Send a file to a peer using peer-to-peer communication."""
        try:
            # Ensure the file exists
            if not os.path.exists(file_path):
                self.log("Error", f"File {file_path} does not exist.")
                return

            # Prepare file metadata to send in the request
            file_metadata = {
                "file_name": os.path.basename(file_path),  # Extract just the file name
                "file_size": os.path.getsize(file_path)  # Add file size for reference
            }

            # Send a file transfer request to the peer
            self.send_udp_message("file_transfer_request", file_metadata, peer_address)
            self.log("File Transfer", f"Sent file transfer request to {peer_address}")

            # Wait for a response with the port for file transfer
            response = self.await_response("file_transfer_port_response", peer_address)

            # Retrieve the port and establish a direct connection
            peer_port = response["port"]
            peer_host, _ = peer_address.split(":")

            # Read the file data
            with open(file_path, "rb") as file:
                file_data = file.read()

            # Establish a TCP connection and send the file
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp_socket:
                tcp_socket.connect((peer_host, peer_port))
                tcp_socket.sendall(file_data)

            self.log("File Sent", f"File {file_path} sent to {peer_host}:{peer_port}")

        except Exception as e:
            self.log("Error", f"Failed to send file {file_path} to {peer_address}: {e}")



    def receive_file(self, port):
        """Receive a file from a peer using a direct TCP connection."""
        def server():
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp_socket:
                tcp_socket.bind(("0.0.0.0", port))  # Bind to specified port
                tcp_socket.listen(1)
                self.log("File Receiver", f"Listening for file transfers on port {port}")

                while self.running:
                    try:
                        client_socket, addr = tcp_socket.accept()
                        threading.Thread(target=self.handle_file_reception, args=(client_socket, addr), daemon=True).start()
                    except Exception as e:
                        self.log("Error", f"File reception error: {e}")
                        break

        threading.Thread(target=server, daemon=True).start()

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