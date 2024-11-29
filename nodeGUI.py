import tkinter as tk
from tkinter import messagebox, scrolledtext, simpledialog, filedialog
from tkinter.ttk import Treeview
import threading
import time
import random
import csv
import sys
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
        tk.Button(txn_frame, text="List Transactions", command=self.list_transactions).pack(side="left", padx=5, pady=5)
        tk.Button(txn_frame, text="Synchronize Transactions", command=self.synchronize_transactions).pack(side="left", padx=5, pady=5)
        tk.Button(txn_frame, text="Query Transactions", command=self.query_transactions).pack(side="left", padx=5, pady=5)
        tk.Button(txn_frame, text="Export Transactions", command=self.export_data).pack(side="left", padx=5, pady=5)

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

    def clear_and_rebuild_data(self):
        confirm = messagebox.askyesno("Clear Data", "Are you sure you want to clear all local data and rebuild from the network?")
        if confirm:
            self.node.clear_local_data()
            self.node.rebuild_from_network()
            self.log_message("Data cleared and rebuild request sent to the network.")
    
    
    def query_transactions_internal(self, sender=None, receiver=None, min_amount=None, max_amount=None):
            results = []
            for txn in self.transactions.values():
                if sender and txn.sender != sender:
                    continue
                if receiver and txn.receiver != receiver:
                    continue
                if min_amount and txn.amount < min_amount:
                    continue
                if max_amount and txn.amount > max_amount:
                    continue
                results.append(txn.to_dict())
            return results
    

    def get_balances(self):
        return self.balances

    def show_balances(self):
        balances = self.get_balances()
        formatted = "\n".join([f"{node}: {balance:.2f}" for node, balance in balances.items()])
        messagebox.showinfo("Balances", formatted)


    def query_transactions(self):
        sender = simpledialog.askstring("Query Transactions", "Enter sender address (optional):")
        receiver = simpledialog.askstring("Query Transactions", "Enter receiver address (optional):")
        min_amount = simpledialog.askfloat("Query Transactions", "Enter minimum amount (optional):")
        max_amount = simpledialog.askfloat("Query Transactions", "Enter maximum amount (optional):")
        results = self.node.query_transactions(sender=sender, receiver=receiver, min_amount=min_amount, max_amount=max_amount)
        if results:
            formatted_results = "\n".join([f"ID: {txn['id']} Sender: {txn['sender']} Receiver: {txn['receiver']} Amount: {txn['amount']} Timestamp: {txn['timestamp']}" for txn in results])
        else:
            formatted_results = "No transactions match the query."
        self.show_query_results(formatted_results)
    
    def log_message(self, message):
        self.log_display.insert(tk.END, f"{message}\n")
        self.log_display.see(tk.END)

    def display_transactions(self, transactions):
        table_window = tk.Toplevel(self.master)
        table_window.title("Transactions")
        tree = Treeview(table_window, columns=("ID", "Sender", "Receiver", "Amount", "Timestamp"), show="headings")
        tree.pack(fill="both", expand=True)
        tree.heading("ID", text="Transaction ID")
        tree.heading("Sender", text="Sender")
        tree.heading("Receiver", text="Receiver")
        tree.heading("Amount", text="Amount")
        tree.heading("Timestamp", text="Timestamp")
        for txn in transactions:
            tree.insert("", tk.END, values=(txn.id, txn.sender, txn.receiver, txn.amount, txn.timestamp))
    
    def show_query_results(self, results):
        result_window = tk.Toplevel(self.master)
        result_window.title("Query Results")
        result_text = scrolledtext.ScrolledText(result_window, wrap=tk.WORD, height=15, width=60)
        result_text.pack(fill="both", expand=True)
        result_text.insert(tk.END, results)
        result_text.config(state="disabled")

    def list_peers(self):
        peers = "\n".join(self.node.peers) if self.node.peers else "No peers connected."
        self.log_message(f"Peers:\n{peers}")

    def add_peer(self):
        peer = simpledialog.askstring("Add Peer", "Enter peer address (IP:PORT):")
        if peer:
            self.node.add_peer(peer)
            self.log_message(f"Added peer: {peer}")

    def request_discovery(self):
        self.node.request_discovery()
        self.log_message("Requested discovery from peers.")

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


    def synchronize_transactions(self):
        self.node.synchronize_transactions()
        self.log_message("Synchronized transactions with peers.")
    
    def remove_peer(self):
        """Remove a peer and close the GUI if the node is being removed."""
        peer = simpledialog.askstring("Remove Peer", "Enter peer address (IP:PORT):")
        if peer in self.node.peers:
            self.node.remove_peer(peer)
            self.log_message(f"Removed peer: {peer}")

            # If the current node is being removed, stop and close the window
            if peer == self.node.address:
                self.log_message("Node is being removed. Closing GUI.")
                self.node.stop()  # Stop the node's operations
            if hasattr(self.master, 'destroy'):
                self.master.destroy()  # Destroy the main Tkinter window
            elif hasattr(self.master, 'quit'):
                self.master.quit()  # Fallback to quit if destroy is unavailable
        else:
            self.log_message(f"Peer not found: {peer}")

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
            "  - Remove Peer: Remove an existing peer.\n"
            "  - Request Discovery: Request peer information from existing peers.\n"
            "  - Join Network: Connect to a peer and join the network.\n\n"
            "Transactions:\n"
            "  - Send Transaction: Send a transaction to a peer.\n"
            "  - List Transactions: View all recorded transactions.\n"
            "  - Query Transactions: Search transactions based on criteria.\n"
            "  - Export Transactions: Save transactions to a CSV file.\n\n"
            "Communication:\n"
            "  - Send Ping: Send a ping to a peer.\n"
            "  - Get Node Details: View the node's details.\n"
            "  - Request Balance: Request balance information from a peer.\n\n"
            "Robot Automation:\n"
            "  - Start Robot: Start automating transactions and pings.\n"
            "  - Stop Robot: Stop the automation.\n"
            "  - Configure Robot: Set automation frequency and max transaction amount.\n\n"
            "Data Management:\n"
            "  - Clear and Rebuild Data: Clear local data and rebuild from the network.\n\n"
            "Logs:\n"
            "  - Logs display real-time activities and errors.\n"
            "  - Use 'Clear Logs' to clear the log display.\n"
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
