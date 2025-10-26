import uvicorn

if __name__ == "__main__":
    app_location = "llm_mock_server.app.main:app"
    print(f"Starting LLM Mock Server. App location: {app_location}")
    uvicorn.run(app_location, host="0.0.0.0", port=8000, reload=True)