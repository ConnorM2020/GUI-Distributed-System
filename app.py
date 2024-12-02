from flask import Flask, jsonify, request

app = Flask(__name__)

# In-memory database (a list of items)
items = [
    {"id": 1, "name": "Item 1", "description": "This is item 1"},
    {"id": 2, "name": "Item 2", "description": "This is item 2"},
]

# Route to get all items
@app.route('/items', methods=['GET'])
def get_items():
    return jsonify(items), 200

# Route to get a specific item by ID
@app.route('/items/<int:item_id>', methods=['GET'])
def get_item(item_id):
    item = next((item for item in items if item["id"] == item_id), None)
    if item is None:
        return jsonify({"error": "Item not found"}), 404
    return jsonify(item), 200

# Route to add a new item
@app.route('/items', methods=['POST'])
def add_item():
    new_item = request.get_json()
    if "name" not in new_item or "description" not in new_item:
        return jsonify({"error": "Invalid item data"}), 400
    new_item["id"] = items[-1]["id"] + 1 if items else 1
    items.append(new_item)
    return jsonify(new_item), 201

# Route to update an existing item
@app.route('/items/<int:item_id>', methods=['PUT'])
def update_item(item_id):
    item = next((item for item in items if item["id"] == item_id), None)
    if item is None:
        return jsonify({"error": "Item not found"}), 404
    updated_data = request.get_json()
    item.update(updated_data)
    return jsonify(item), 200

# Route to delete an item
@app.route('/items/<int:item_id>', methods=['DELETE'])
def delete_item(item_id):
    global items
    items = [item for item in items if item["id"] != item_id]
    return jsonify({"message": "Item deleted"}), 200

if __name__ == '__main__':
    app.run(debug=True)
