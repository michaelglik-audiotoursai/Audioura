def orchestrate_tour_async(job_id, location, tour_type, total_stops, user_id, request_string):
    """Orchestrate the complete tour generation pipeline asynchronously."""
    try:
        print(f"\n==== ORCHESTRATE_TOUR_ASYNC FUNCTION CALLED ====")
        print(f"Parameters:")
        print(f"  job_id: {job_id}")
        print(f"  location: {location}")
        print(f"  tour_type: {tour_type}")
        print(f"  total_stops: {total_stops}")
        print(f"  user_id: {user_id}")
        print(f"  request_string: {request_string}")
        
        # Step 1: Generate tour text
        print(f"\n==== STEP 1: GENERATING TOUR TEXT ====\n")
        print(f"Generating tour text for {location} - {tour_type} Tour")
        ACTIVE_JOBS[job_id]["progress"] = "Step 1/8: Generating tour text..."
        
        try:
            # Prepare data for the tour generator service
            tour_data = {
                "location": location,
                "tour_type": tour_type,
                "total_stops": total_stops
            }
            
            # Call the tour generator service
            response = requests.post(
                "http://tour-generator:5000/generate",
                json=tour_data,
                timeout=120  # Increased timeout for tour generation
            )
            
            if response.status_code != 200:
                raise Exception(f"Tour generator service returned status code {response.status_code}: {response.text}")
            
            # Parse the response
            result = response.json()
            tour_text = result.get("tour_text")
            
            if not tour_text:
                raise Exception("Tour generator service returned empty tour text")
            
            print(f"Tour text generation completed successfully")
            
            # Save the tour text to a file
            tour_filename = f"{location.replace(' ', '_')}_{tour_type}_{job_id[:8]}.txt"
            tour_path = os.path.join(TOURS_DIR, tour_filename)
            
            with open(tour_path, "w") as f:
                f.write(tour_text)
            
            print(f"Tour text saved to {tour_path}")
            
        except Exception as e:
            print(f"ERROR generating tour text: {e}")
            raise Exception(f"Error in tour generation: {e}")
        
        # Step 2: Process tour text into audio files
        print(f"\n==== STEP 2: PROCESSING TOUR TEXT INTO AUDIO ====\n")
        ACTIVE_JOBS[job_id]["progress"] = "Step 2/8: Processing tour text into audio files..."
        
        try:
            # Prepare data for the tour processor service
            process_data = {
                "tour_file": tour_filename
            }
            
            # Call the tour processor service
            response = requests.post(
                "http://tour-processor:5001/process",
                json=process_data,
                timeout=300  # Increased timeout for audio processing
            )
            
            if response.status_code != 200:
                raise Exception(f"Tour processor service returned status code {response.status_code}: {response.text}")
            
            # Parse the response
            result = response.json()
            processor_job_id = result.get("job_id")
            
            if not processor_job_id:
                raise Exception("Tour processor service did not return a job ID")
            
            print(f"Tour processing started with job ID: {processor_job_id}")
            
            # Poll for job completion
            max_retries = 60  # 10 minutes with 10-second intervals
            for i in range(max_retries):
                time.sleep(10)  # Wait 10 seconds between polls
                
                # Check job status
                status_response = requests.get(
                    f"http://tour-processor:5001/status/{processor_job_id}",
                    timeout=30
                )
                
                if status_response.status_code != 200:
                    raise Exception(f"Failed to get job status: {status_response.status_code}: {status_response.text}")
                
                status_result = status_response.json()
                job_status = status_result.get("status")
                job_progress = status_result.get("progress", "")
                
                print(f"Tour processing status: {job_status} - {job_progress}")
                ACTIVE_JOBS[job_id]["progress"] = f"Step 2/8: {job_progress}"
                
                if job_status == "completed":
                    # Get the output ZIP file
                    zip_filename = status_result.get("output_zip")
                    if not zip_filename:
                        raise Exception("Tour processor did not return an output ZIP file")
                    
                    print(f"Tour processing completed successfully: {zip_filename}")
                    break
                elif job_status == "error":
                    error_message = status_result.get("error", "Unknown error")
                    raise Exception(f"Tour processing failed: {error_message}")
                
                if i == max_retries - 1:
                    raise Exception("Tour processing timed out")
            
        except Exception as e:
            print(f"ERROR processing tour text: {e}")
            raise Exception(f"Error in tour processing: {e}")
        
        # Step 3: Extract the ZIP file
        print(f"\n==== STEP 3: EXTRACTING TOUR PACKAGE ====\n")
        ACTIVE_JOBS[job_id]["progress"] = "Step 3/8: Extracting tour package..."
        
        try:
            # Download the ZIP file
            download_response = requests.get(
                f"http://tour-processor:5001/download/{processor_job_id}",
                timeout=60
            )
            
            if download_response.status_code != 200:
                raise Exception(f"Failed to download tour package: {download_response.status_code}: {download_response.text}")
            
            # Save the ZIP file
            zip_path = os.path.join(TOURS_DIR, zip_filename)
            with open(zip_path, "wb") as f:
                f.write(download_response.content)
            
            print(f"Tour package downloaded to {zip_path}")
            
            # Extract the ZIP file
            extract_dir = f"{location.replace(' ', '_')}_{tour_type}_{job_id[:8]}"
            extract_path = os.path.join(TOURS_DIR, extract_dir)
            os.makedirs(extract_path, exist_ok=True)
            
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                zip_ref.extractall(extract_path)
            
            print(f"Tour package extracted to {extract_path}")
            
        except Exception as e:
            print(f"ERROR extracting tour package: {e}")
            raise Exception(f"Error in tour extraction: {e}")
        
        # Step 4-7: Get coordinates for the location
        print(f"\n==== STEP 4-7: GETTING COORDINATES ====\n")
        ACTIVE_JOBS[job_id]["progress"] = "Step 4-7/8: Getting coordinates for location..."
        
        lat = None
        lng = None
        
        try:
            # Try to get coordinates from the coordinates-fromai service
            coords = get_coordinates_direct(location)
            print(f"Result from get_coordinates_for_location: {coords}")
            if coords:
                lat, lng = coords
                print(f"Successfully got coordinates in final attempt: lat={lat}, lng={lng}")
            else:
                print(f"WARNING: Could not get coordinates for {location} in final attempt")
        except Exception as e:
            print(f"ERROR getting coordinates: {e}")
            print(f"WARNING: Could not get coordinates for {location}")
        
        # Step 8: Store in database
        print(f"\n==== STEP 8: STORING TOUR IN DATABASE ====\n")
        print(f"Tour name: {location} - {tour_type} Tour")
        print(f"Request string: {request_string or location}")
        print(f"Coordinates to store: lat={lat}, lng={lng}")
        ACTIVE_JOBS[job_id]["progress"] = "Step 8/8: Storing tour in database..."
        
        # Store the tour in the database
        tour_name = f"{location} - {tour_type} Tour"
        print(f"Storing tour in database: {tour_name}")
        print(f"Coordinates being stored: lat={lat}, lng={lng}")
        
        store_success = store_audio_tour(tour_name, request_string or location, zip_path, lat, lng)
        
        print(f"\n==== STORE_AUDIO_TOUR RESULT ====\n")
        print(f"Success: {store_success}")
        
        if store_success:
            ACTIVE_JOBS[job_id]["progress"] = "Tour stored in database successfully!"
            print(f"Tour stored successfully with coordinates: lat={lat}, lng={lng}")
        else:
            ACTIVE_JOBS[job_id]["progress"] = "Warning: Tour generated but could not be stored in database."
            print("Failed to store tour in database")
        
        # Complete
        ACTIVE_JOBS[job_id]["progress"] = "Tour generation completed successfully!"
        ACTIVE_JOBS[job_id]["status"] = "completed"
        ACTIVE_JOBS[job_id]["output_zip"] = zip_filename
        ACTIVE_JOBS[job_id]["extract_dir"] = extract_dir
        ACTIVE_JOBS[job_id]["netlify_ready"] = True
        ACTIVE_JOBS[job_id]["coordinates"] = [lat, lng] if lat and lng else None
        
    except Exception as e:
        print(f"ERROR in orchestrate_tour_async: {e}")
        ACTIVE_JOBS[job_id]["status"] = "error"
        ACTIVE_JOBS[job_id]["error"] = str(e)