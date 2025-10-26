import uvicorn

if __name__ == "__main__":
    app_location = "apim_server.apim_server:app"
    print(f"Starting APIM Server (Gateway). App location: {app_location}")
    uvicorn.run(app_location, host="0.0.0.0", port=8001, reload=True)