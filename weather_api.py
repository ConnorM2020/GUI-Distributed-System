from flask import Flask, jsonify, request
import requests
from node import Node

app = Flask(__name__)

# Your OpenWeatherMap API key
OPENWEATHER_API_KEY = "your_api_key_here"  # Replace with your OpenWeatherMap API key

# Initialize the Node instance
node = Node("WeatherNode", "127.0.0.0:5001")  # Ensure this port is available

@app.route("/weather", methods=["GET"])
def get_weather():
    """
    Fetch weather data for a given city using the OpenWeatherMap API.
    """
    city = request.args.get("city", default="London")  # Default city is London
    if not city:
        return jsonify({"error": "City is required"}), 400

    try:
        # OpenWeatherMap API endpoint
        weather_url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={OPENWEATHER_API_KEY}&units=metric"
        response = requests.get(weather_url)

        if response.status_code != 200:
            node.log("Weather API Error", f"Failed to fetch weather for {city}. HTTP {response.status_code}")
            return jsonify({"error": "Unable to fetch weather data"}), response.status_code

        # Parse the weather data
        weather_data = response.json()
        result = {
            "city": weather_data.get("name"),
            "temperature": weather_data["main"]["temp"],
            "weather": weather_data["weather"][0]["description"],
            "humidity": weather_data["main"]["humidity"],
            "wind_speed": weather_data["wind"]["speed"],
        }

        # Log the successful weather fetch in the Node system
        node.log("Weather Fetch Success", f"Fetched weather for {city}: {result}")
        return jsonify(result)

    except Exception as e:
        # Log the error in the Node system
        node.log("Weather Fetch Error", f"Error fetching weather for {city}: {str(e)}")
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500


@app.route("/node_status", methods=["GET"])
def get_node_status():
    """
    Retrieve the status of the node, including peers and balances.
    """
    try:
        status = {
            "node_id": node.node_id,
            "nickname": node.nickname,
            "address": node.address,
            "balances": node.balances,
            "peers": node.peers,
        }
        return jsonify(status)
    except Exception as e:
        node.log("Node Status Error", f"Error retrieving node status: {str(e)}")
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500


@app.route("/log", methods=["POST"])
def log_message():
    """
    Log a custom message in the Node system.
    """
    data = request.json
    log_type = data.get("type", "General")
    message = data.get("message", "No message provided")
    node.log(log_type, message)
    return jsonify({"status": "Log added successfully"}), 200


if __name__ == "__main__":
    # Run the Flask app
    app.run(host="0.0.0.0", port=5000, debug=True)  # Ensure port 6080 is available
