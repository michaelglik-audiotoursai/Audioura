from flask import Flask, jsonify, request
from flask_cors import CORS
import uuid

app = Flask(__name__)
CORS(app)

mock_tours = [
    {
        "id": "tour-1",
        "title": "Metropolitan Museum Tour",
        "location": "Metropolitan Museum, NYC",
        "type": "museum",
        "latitude": 40.7794,
        "longitude": -73.9632,
        "icon": "frame",
        "popular": True,
        "stops": [{"id": "stop-1", "title": "Egyptian Art", "audio_url": "/mock/audio1.mp3", "description": "Ancient artifacts"}]
    },
    {
        "id": "tour-2",
        "title": "Central Park Bike Tour",
        "location": "Central Park, NYC",
        "type": "bike",
        "latitude": 40.7829,
        "longitude": -73.9654,
        "icon": "bicycle",
        "popular": True,
        "stops": [{"id": "stop-1", "title": "Bethesda Fountain", "audio_url": "/mock/audio2.mp3", "description": "Historic fountain"}]
    },
    {
        "id": "tour-3",
        "title": "Manhattan Auto Tour",
        "location": "Times Square, NYC",
        "type": "auto",
        "latitude": 40.7580,
        "longitude": -73.9855,
        "icon": "car",
        "popular": True,
        "stops": [{"id": "stop-1", "title": "Broadway", "audio_url": "/mock/audio3.mp3", "description": "Theater district"}]
    }
]

@app.route('/tours', methods=['GET'])
def get_tours():
    return jsonify(mock_tours)

@app.route('/tours/<tour_id>', methods=['GET'])
def get_tour(tour_id):
    tour = next((t for t in mock_tours if t['id'] == tour_id), None)
    if tour:
        return jsonify(tour)
    return jsonify({"error": "Tour not found"}), 404

@app.route('/tours/nearby', methods=['GET'])
def get_nearby_tours():
    lat = request.args.get('lat', type=float)
    lng = request.args.get('lng', type=float)
    radius = request.args.get('radius', 5, type=int)
    
    # Return all tours for demo (in real app, filter by distance)
    return jsonify(mock_tours)

@app.route('/tours/popular', methods=['GET'])
def get_popular_tours():
    popular = [t for t in mock_tours if t.get('popular', False)]
    return jsonify(popular)

@app.route('/tours', methods=['POST'])
def create_tour():
    data = request.json
    new_tour = {
        "id": str(uuid.uuid4()),
        "title": f"{data['location']} {data['tour_type']} Tour",
        "location": data['location'],
        "stops": [
            {"id": f"stop-{i}", "title": f"Stop {i}", "audio_url": f"/mock/audio{i}.mp3", "description": f"Description {i}"}
            for i in range(1, data['total_stops'] + 1)
        ]
    }
    mock_tours.append(new_tour)
    return jsonify(new_tour), 201

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5004, debug=True)