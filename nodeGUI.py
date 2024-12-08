import tkinter as tk
from tkinter import messagebox, scrolledtext, simpledialog, filedialog
from tkinter.ttk import Treeview
import threading
import time
import random
import csv
import sys
import requests
from node import Node
from node import Node, Transaction
from tkinter import filedialog


class NodeGUI:
    def __init__(self, master, port, ip="0.0.0.0"):
        self.master = master
        self.node_name = f"Node-{port}"
        self.master.title(f"{self.node_name} GUI")
        self.node = None
        self.robot_running = False  # Flag for the robot
        self.robot_frequency = 5  # Default robot frequency (seconds)
        self.robot_max_amount = 50.0  # Default maximum transaction amount for the robot
        self.setup_gui()
     
        self.node = Node(self.node_name, f"{ip}:{port}", log_callback=self.log_message)
        threading.Thread(target=self.node.listen, daemon=True).start()

    def setup_gui(self):
        # Display Node Name
        tk.Label(self.master, text=f"Node: {self.node_name}", font=("Arial", 16)).pack(pady=10)

        # Peer Management
        peer_frame = tk.LabelFrame(self.master, text="Peer Management", padx=5, pady=5)
        peer_frame.pack(fill="x", padx=10, pady=5)
        tk.Button(peer_frame, text="List Peers", command=self.list_peers).pack(side="left", padx=5, pady=5)
        tk.Button(peer_frame, text="Add Peer", command=self.add_peer).pack(side="left", padx=5, pady=5)
        tk.Button(peer_frame, text="Remove Current Node", command=self.remove_current_node).pack(side="left", padx=5, pady=5)
        tk.Button(peer_frame, text="Remove Peer", command=self.remove_peer).pack(side="left", padx=5, pady=5)
        tk.Button(peer_frame, text="Request Discovery", command=self.request_discovery).pack(side="left", padx=5, pady=5)
        tk.Button(peer_frame, text="Join Network", command=self.join_network).pack(side="left", padx=5, pady=5)

        # Transactions
        txn_frame = tk.LabelFrame(self.master, text="Transactions", padx=5, pady=5)
        txn_frame.pack(fill="x", padx=10, pady=5)
        tk.Button(txn_frame, text="Send Transaction", command=self.send_transaction).pack(side="left", padx=5, pady=5)
        tk.Button(txn_frame, text="Send Custom Transaction", command=self.send_custom_transaction_gui).pack(side="left", padx=5, pady=5)
        tk.Button(txn_frame, text="List Transactions", command=self.list_transactions).pack(side="left", padx=5, pady=5)
        tk.Button(txn_frame, text="Synchronize Transactions", command=self.synchronize_transactions).pack(side="left", padx=5, pady=5)
        tk.Button(txn_frame, text="Export Transactions", command=self.export_data).pack(side="left", padx=5, pady=5)
        tk.Button(txn_frame, text="Retrieve Transaction by Index", command=self.retrieve_transaction_by_index).pack(side="left", padx=5, pady=5)

        # Communication
        comm_frame = tk.LabelFrame(self.master, text="Communication", padx=5, pady=5)
        comm_frame.pack(fill="x", padx=10, pady=5)
        tk.Button(comm_frame, text="Send Ping", command=self.send_ping).pack(side="left", padx=5, pady=5)
        tk.Button(comm_frame, text="Get Node Details", command=self.get_node_details).pack(side="left", padx=5, pady=5)
        tk.Button(comm_frame, text="Request Balance", command=self.request_balance).pack(side="left", padx=5, pady=5)

        # Robot automation
        robot_frame = tk.LabelFrame(self.master, text="Robot Automation", padx=5, pady=5)
        robot_frame.pack(fill="x", padx=10, pady=5)
        tk.Button(robot_frame, text="Start Robot", command=self.start_robot).pack(side="left", padx=5, pady=5)
        tk.Button(robot_frame, text="Stop Robot", command=self.stop_robot).pack(side="left", padx=5, pady=5)

        # Data Management
        data_frame = tk.LabelFrame(self.master, text="Data Management", padx=5, pady=5)
        data_frame.pack(fill="x", padx=10, pady=5)
        tk.Button(data_frame, text="Clear and Rebuild Data", command=self.clear_and_rebuild_data).pack(side="left", padx=5, pady=5)


         # File Transfer Section
        file_transfer_frame = tk.LabelFrame(self.master, text="File Transfers", padx=5, pady=5)
        file_transfer_frame.pack(fill="x", padx=10, pady=5)
        tk.Button(file_transfer_frame, text="Send File", command=self.send_file_gui).pack(side="left", padx=5, pady=5)

        # Log area
        log_frame = tk.LabelFrame(self.master, text="Logs", padx=5, pady=5)
        log_frame.pack(fill="both", expand=True, padx=10, pady=5)
        self.log_display = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, height=15)
        self.log_display.pack(fill="both", expand=True)
        tk.Button(log_frame, text="Clear Logs", command=self.clear_logs).pack(pady=5)

        # Menu
        menu = tk.Menu(self.master)
        help_menu = tk.Menu(menu, tearoff=0)
        help_menu.add_command(label="Help", command=self.show_help)
        menu.add_cascade(label="Help", menu=help_menu)
        self.master.config(menu=menu)


    def send_file_gui(self):
        """GUI method to send a file."""
        file_path = filedialog.askopenfilename(title="Select File to Send")
        if not file_path:
            self.log_message("File Transfer Cancelled")
            return

        receiver = simpledialog.askstring("Send File", "Enter receiver address (IP:PORT):")
        if not receiver:
            self.log_message("Receiver address not provided.")
            return

        try:
            self.node.send_file(file_path, receiver)
            self.log_message(f"File {file_path} sent to {receiver}")
        except Exception as e:
            self.log_message(f"Error: {e}")

            
    def clear_and_rebuild_data(self):
        confirm = messagebox.askyesno("Clear Data", "Are you sure you want to clear all local data and rebuild from the network?")
        if confirm:
            self.node.clear_local_data()
            self.node.rebuild_from_network()
            self.log_message("Data cleared and rebuild request sent to the network.")
    
    def get_balances(self):
        return self.balances

    def send_transaction_with_file(self):
        """Send a transaction with a linked file."""
        receiver = simpledialog.askstring("Send Transaction", "Enter receiver address:")
        if not receiver:
            return
        try:
            amount = float(simpledialog.askstring("Send Transaction", "Enter amount:"))
            file_path = filedialog.askopenfilename(title="Select File to Attach")
            txn = Transaction(amount=amount, sender=self.node.address, receiver=receiver, file_path=file_path)

            # Add the transaction to local records
            self.node.transactions[txn.id] = txn
            self.node.broadcast_transaction(txn)
            self.node.send_file(file_path, receiver)
            self.log_message(f"Transaction with file sent to {receiver} with amount {amount}. File: {file_path}")
        except ValueError:
            self.log_message("Invalid amount entered.")


    def show_balances(self):
        balances = self.get_balances()
        formatted = "\n".join([f"{node}: {balance:.2f}" for node, balance in balances.items()])
        messagebox.showinfo("Balances", formatted)

    def log_message(self, message):
        self.log_display.insert(tk.END, f"{message}\n")
        self.log_display.see(tk.END)

    def display_transactions(self, transactions):
        table_window = tk.Toplevel(self.master)
        table_window.title("Transactions")

        tree = Treeview(
            table_window,
            columns=("ID", "Sender", "Receiver", "Amount", "Timestamp", "Custom Fields"),
            show="headings"
        )
        tree.pack(fill="both", expand=True)

        tree.heading("ID", text="Transaction ID")
        tree.heading("Sender", text="Sender")
        tree.heading("Receiver", text="Receiver")
        tree.heading("Amount", text="Amount")
        tree.heading("Timestamp", text="Timestamp")
        tree.heading("Custom Fields", text="Custom Fields")

        for txn in transactions:
            # Convert custom fields to string for display
            custom_fields_str = ", ".join(f"{k}: {v}" for k, v in txn.custom_fields.items()) if txn.custom_fields else "None"
            tree.insert("", tk.END, values=(txn.id, txn.sender, txn.receiver, txn.amount, txn.timestamp, custom_fields_str))

        tk.Button(table_window, text="Close", command=table_window.destroy).pack(pady=5)

    def retrieve_transaction_by_index(self):
        try:
            # Get the transaction index from the user
            index = simpledialog.askinteger("Retrieve Transaction", "Enter the transaction index (0-based):")
            if index is None:
                return  # User canceled the input dialog

            # Call the node method to retrieve the transaction
            transaction = self.node.get_transaction_by_index(index)

            # Check if the transaction was found or if there was an error
            if "error" in transaction:
                messagebox.showerror("Error", transaction["error"])
            else:
                # Display the transaction details
                details = (
                    f"ID: {transaction['id']}\n"
                    f"Sender: {transaction['sender']}\n"
                    f"Receiver: {transaction['receiver']}\n"
                    f"Amount: {transaction['amount']}\n"
                    f"Timestamp: {transaction['timestamp']}"
                )
                messagebox.showinfo("Transaction Details", details)
        except Exception as e:
            self.log_message(f"Error: {e}")

    def list_peers(self):
        peers = "\n".join(self.node.peers) if self.node.peers else "No peers connected."
        self.log_message(f"Peers:\n{peers}")

    def add_peer(self):
        peer = simpledialog.askstring("Add Peer", "Enter peer address (IP:PORT):")
        if peer:
            self.node.add_peer(peer)
            self.log_message(f"Added peer: {peer}")

    def request_discovery(self):
        user_input = simpledialog.askstring("Request Discovery", "Enter discovery nodes (comma-separated IPs):")
        if user_input:
            try:
                # Parse the IPs and validate
                peer_ips = [ip.strip() for ip in user_input.split(",") if ip.strip()]
                self.node.request_discovery(peer_ips)  # Pass the list of IPs
                self.log_message(f"Requested discovery from: {', '.join(peer_ips)}")
            except Exception as e:
                self.log_message(f"Error during discovery: {e}")


    def join_network(self):
        peer = simpledialog.askstring("Join Network", "Enter peer address (IP:PORT):")
        if peer:
            self.node.join_network(peer)
            self.log_message(f"Joined network via {peer}")

    def send_transaction(self):
        receiver = simpledialog.askstring("Send Transaction", "Enter receiver address:")
        if not receiver:
            return
        try:
            amount = float(simpledialog.askstring("Send Transaction", "Enter amount:"))
            self.node.send_transaction(receiver, amount)
            self.log_message(f"Sent transaction to {receiver} with amount {amount}")
        except ValueError:
            self.log_message("Invalid amount entered.")

    def list_transactions(self):
        transactions = list(self.node.transactions.values())
        if transactions:
            formatted_transactions = "\n".join([
                f"ID: {txn.id}\n"
                f"Sender: {txn.sender}\n"
                f"Receiver: {txn.receiver}\n"
                f"Amount: {txn.amount}\n"
                f"Timestamp: {txn.timestamp}\n"
                "-----------------------------------"
                for txn in transactions
            ])
            self.log_message(f"Transactions:\n{formatted_transactions}")
        else:
            self.log_message("No transactions found.")
        self.display_transactions(transactions)
        
    def send_custom_transaction_gui(self):
        receiver = simpledialog.askstring("Send Custom Transaction", "Enter receiver address:")
        if not receiver:
            return
        try:
            amount = float(simpledialog.askstring("Send Custom Transaction", "Enter amount:"))
            custom_fields = {}

            # Ask for custom fields in a loop
            while True:
                custom_key = simpledialog.askstring("Custom Field Key", "Enter custom field key (or leave blank to finish):")
                if not custom_key:
                    break
                custom_value = simpledialog.askstring("Custom Field Value", f"Enter value for {custom_key}:")
                if custom_value is not None:
                    custom_fields[custom_key] = custom_value  # Add key-value pair to the dictionary

            print(f"Custom fields being sent: {custom_fields}")  # Debugging: Check custom fields

            # Call the backend method to send the custom transaction
            self.node.send_custom_transaction(receiver, amount, **custom_fields)
            self.log_message(f"Custom transaction sent to {receiver} with {amount} and custom fields {custom_fields}.")
        except ValueError:
            self.log_message("Invalid amount entered.")


    def synchronize_transactions(self):
            self.node.synchronize_transactions()
            self.log_message("Synchronized transactions with peers.")
        

    def remove_peer(self):
        """Remove a peer from self.node.peers and reject their messages."""
        # Prompt the user for the peer address
        peer = simpledialog.askstring("Remove Peer", "Enter peer address (IP:PORT):").strip()
        print(f"Peer node wanting to remove: {peer}")
        if not peer:  # Check if peer is None or an empty string
            self.log_message("Peer address cannot be empty.\n")
            return
        
        if peer in self.node.peers:
            self.node.peers.remove(peer)  
            self.log_message(f"Peer {peer} successfully removed from the network.")

            # Modify handle_udp_message to reject messages from removed peers
            def updated_handle_udp_message(data, addr):
                sender_address = f"{addr[0]}:{addr[1]}"
                if sender_address == peer:
                    return
                self.node.handle_udp_message(data, addr)

            # Replace the original message handler with the updated one
            self.node.handle_udp_message = updated_handle_udp_message

            self.log_message(f"Messages from {peer} will now be rejected.")
            print(f"Updated message handling to reject messages from {peer}.")
        else:
            self.log_message(f"Peer {peer} not found in the network.")


    def remove_current_node(self):
        """Remove the current node and close the GUI."""
        confirm = messagebox.askyesno("Remove Current Node", "Are you sure you want to remove this node? This will close the GUI.")
        if confirm:
            self.node.stop()  # Stop the node's operations
            self.log_message("Current node removed. Closing GUI.")
            if hasattr(self.master, 'destroy'):
                self.master.destroy()  # Destroy the main Tkinter window
            elif hasattr(self.master, 'quit'):
                self.master.quit()  # Fallback to quit if destroy is unavailable


    def toggle_failure_simulation(self):
        self.node.failure_simulation = not self.node.failure_simulation
        status = "enabled" if self.node.failure_simulation else "disabled"
        self.log_message(f"Failure simulation {status}.")

    def send_ping(self):
        peer = simpledialog.askstring("Send Ping", "Enter peer address (IP:PORT):")
        if peer:
            self.node.send_udp_message("ping", {"data": "Ping"}, peer)
            self.log_message(f"Ping sent to {peer}")


    def get_node_details(self):
        # Create the main details window
        details_window = tk.Toplevel(self.master)
        details_window.title("Node Details")

        # Display node name and address
        tk.Label(details_window, text=f"Node Name: {self.node.nickname}", font=("Arial", 14)).pack(pady=5)
        tk.Label(details_window, text=f"Address: {self.node.address}", font=("Arial", 12)).pack(pady=5)

        # Display current node's balance
        current_balance = self.node.balances.get(self.node.address, 0.0)  # Default to 0.0 if not found
        tk.Label(details_window, text=f"Current Balance: {current_balance:.2f}", font=("Arial", 12, "bold"), fg="green").pack(pady=5)

        # Send balance requests to all connected peers
        for peer in self.node.peers:
            self.node.send_udp_message("balance_request", {}, peer, silent=True)

        # Create a frame for peers and balances
        peers_frame = tk.LabelFrame(details_window, text="Connected Peers and Balances")
        peers_frame.pack(fill="both", expand=True, padx=10, pady=5)

        # Headers for peers and balances
        tk.Label(peers_frame, text="Peer Address", font=("Arial", 10, "bold")).grid(row=0, column=0, padx=10, pady=5)
        tk.Label(peers_frame, text="Balance", font=("Arial", 10, "bold")).grid(row=0, column=1, padx=10, pady=5)

        # Populate peers and balances
        for idx, peer in enumerate(self.node.peers, start=1):
            balance = self.node.balances.get(peer, "Unknown")  # Retrieve peer balance or mark as "Unknown"
            tk.Label(peers_frame, text=peer, font=("Arial", 10)).grid(row=idx, column=0, padx=10, pady=5, sticky="w")
            tk.Label(peers_frame, text=f"{balance:.2f}" if isinstance(balance, (float, int)) else balance, font=("Arial", 10)).grid(row=idx, column=1, padx=10, pady=5, sticky="e")

        # Create a frame for transactions
        transaction_frame = tk.LabelFrame(details_window, text="Transactions")
        transaction_frame.pack(fill="both", expand=True, padx=10, pady=5)

        # Display transactions using the existing display_transactions function
        self.display_transactions(list(self.node.transactions.values()))

        # Close button
        tk.Button(details_window, text="Close", command=details_window.destroy).pack(pady=10)

    def request_balance(self):
        peer = simpledialog.askstring("Request Balance", "Enter peer address (IP:PORT):")
        if peer:
            self.node.send_udp_message("balance_request", {}, peer)
            self.log_message(f"Requested balance from {peer}")

    def start_robot(self):
        """Start automated robot tasks."""
        self.robot_running = True
        threading.Thread(target=self.robot_task, daemon=True).start()
        self.log_message("Robot started.")

    def stop_robot(self):
        """Stop automated robot tasks."""
        self.robot_running = False
        self.log_message("Robot stopped.")

    def robot_task(self):
        """Perform automated tasks in a loop."""
        while self.robot_running:
            if not self.node.peers:
                time.sleep(1)
                continue
            # Randomly select actions
            action = random.choice(["transaction", "ping", "balance"])
            peer = random.choice(self.node.peers)
            if action == "transaction":
                amount = random.uniform(1, 50)
                self.node.send_transaction(peer, amount)
                self.log_message(f"Robot: Sent transaction to {peer} with amount {amount:.2f}")
            elif action == "ping":
                self.node.send_udp_message("ping", {"data": "Ping from robot"}, peer)
                self.log_message(f"Robot: Pinged {peer}")
            elif action == "balance":
                self.node.send_udp_message("balance_request", {}, peer)
                self.log_message(f"Robot: Requested balance from {peer}")
            time.sleep(random.randint(2, 5))  # Delay between actions

    def clear_logs(self):
        """Clear the log area."""
        self.log_display.delete('1.0', tk.END)

    def export_data(self):
        file_path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV Files", "*.csv")])
        if not file_path:
            return

        with open(file_path, "w", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(["ID", "Sender", "Receiver", "Amount", "Timestamp"])
            for txn in self.node.transactions.values():
                writer.writerow([txn.id, txn.sender, txn.receiver, txn.amount, txn.timestamp])

        self.log_message(f"Data exported to {file_path}")

    def show_help(self):
        help_text = (
            "NodeGUI Help:\n\n"
            "Peer Management:\n"
            "  - List Peers: Display all connected peers.\n"
            "  - Add Peer: Add a new peer by providing its IP:PORT.\n"
            "  - Remove Current Node: Remove the current node and close the application.\n"
            "  - Remove Peer: Remove a specific peer from the network.\n"
            "  - Request Discovery: Request peer information from existing peers.\n"
            "  - Join Network: Connect to a peer and join its network.\n\n"
            "Transactions:\n"
            "  - Send Transaction: Create and send a transaction to a peer.\n"
            "  - List Transactions: Display all recorded transactions in the node.\n"
            "  - Synchronize Transactions: Sync transactions with peers to ensure consistency.\n"
            "  - Export Transactions: Save all transactions as a CSV file.\n"
            "  - Retrieve Transaction by Index: Fetch transaction details using a 0-based index.\n\n"
            "Communication:\n"
            "  - Send Ping: Send a ping message to a peer to check connectivity.\n"
            "  - Get Node Details: View details about the current node, including balances and peers.\n"
            "  - Request Balance: Request the balance from a specific peer.\n\n"
            "Robot Automation:\n"
            "  - Start Robot: Start automated actions like transactions and pings.\n"
            "  - Stop Robot: Stop the automated actions.\n\n"
            "Data Management:\n"
            "  - Clear and Rebuild Data: Clear local data and rebuild the state from the network.\n\n"
            "Logs:\n"
            "  - Logs display real-time activities, actions, and errors.\n"
            "  - Clear Logs: Clear the current log display.\n"
        )
        messagebox.showinfo("Help", help_text)


def start_gui(port, ip="0.0.0.0"):
    root = tk.Tk()
    app = NodeGUI(root, port, ip)
    root.protocol("WM_DELETE_WINDOW", lambda: app.node.stop() or root.destroy())
    root.mainloop()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python nodeGUI.py <port> [<ip>]")
        sys.exit(1)

    port = int(sys.argv[1])
    ip = sys.argv[2] if len(sys.argv) > 2 else "0.0.0.0"
    start_gui(port, ip)