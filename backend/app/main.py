from fastapi import FastAPI

app = FastAPI(title="API Backend")

@app.get("/health")
def health_check():
    return {"status": "ok"}