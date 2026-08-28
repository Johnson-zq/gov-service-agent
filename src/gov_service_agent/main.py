from fastapi import FastAPI

app = FastAPI(title="gov-service-agent")


@app.get("/health")
def health():
    return {"status": "ok"}
