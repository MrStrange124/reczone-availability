import uvicorn

if __name__ == "__main__":
    uvicorn.run("reczone.server:app", host="127.0.0.1", port=8765, reload=True)
