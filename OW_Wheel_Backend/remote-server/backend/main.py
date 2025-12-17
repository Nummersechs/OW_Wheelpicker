import os
from datetime import datetime  # für Pydantic-Typen
from typing import Optional, List

from fastapi import FastAPI, Depends, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    Float,
    String,
    DateTime,
    func,
)
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from fastapi.responses import HTMLResponse

# --------------------------------------------------------------------
# DB-Setup
# --------------------------------------------------------------------

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is not set")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# --------------------------------------------------------------------
# Models (SQLAlchemy)
# --------------------------------------------------------------------

class Entry(Base):
    __tablename__ = "entries"

    id = Column(Integer, primary_key=True, index=True)
    source = Column(String, index=True)
    value = Column(Float)
    # Timestamp von der DB setzen lassen (timezone-aware in Postgres)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True,
    )


class SpinResult(Base):
    __tablename__ = "spin_results"

    id = Column(Integer, primary_key=True, index=True)

    tank1 = Column(String, index=True)
    tank2 = Column(String, index=True)
    dps1 = Column(String, index=True)
    dps2 = Column(String, index=True)
    support1 = Column(String, index=True)
    support2 = Column(String, index=True)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True,
    )
    
class RoleName(Base):
    __tablename__ = "role_names"

    id = Column(Integer, primary_key=True, index=True)
    role = Column(String, index=True)      # "Tank", "Damage", "Support"
    position = Column(Integer, index=True) # Reihenfolge
    name = Column(String, index=True)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True,
    )


# --------------------------------------------------------------------
# Pydantic-Schemas
# --------------------------------------------------------------------

class EntryIn(BaseModel):
    source: str
    value: float


class EntryOut(BaseModel):
    id: int
    source: str
    value: float
    created_at: datetime

    class Config:
        # Pydantic v2: statt orm_mode = True
        from_attributes = True


class SpinResultIn(BaseModel):
    tank1: str
    tank2: str
    dps1: str
    dps2: str
    support1: str
    support2: str


class SpinResultOut(BaseModel):
    id: int
    tank1: str
    tank2: str
    dps1: str
    dps2: str
    support1: str
    support2: str
    created_at: datetime

    class Config:
        # Pydantic v2
        from_attributes = True

class RoleNamesIn(BaseModel):
    role: str
    names: List[str]

class RolesSyncIn(BaseModel):
    roles: List[RoleNamesIn]


# --------------------------------------------------------------------
# WebSocket ConnectionManager
# --------------------------------------------------------------------

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def send_json(self, websocket: WebSocket, message: dict):
        await websocket.send_json(message)

    async def broadcast_json(self, message: dict):
        for connection in self.active_connections:
            await connection.send_json(message)


manager = ConnectionManager()


# --------------------------------------------------------------------
# FastAPI-App
# --------------------------------------------------------------------

app = FastAPI(title="Remote Data Server")


# -------------------- Basis-Endpoints --------------------

@app.post("/data", response_model=EntryOut)
def insert_data(entry: EntryIn, db: Session = Depends(get_db)):
    obj = Entry(source=entry.source, value=entry.value)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@app.get("/latest", response_model=Optional[EntryOut])
def get_latest(source: str, db: Session = Depends(get_db)):
    obj = (
        db.query(Entry)
        .filter(Entry.source == source)
        .order_by(Entry.created_at.desc())
        .first()
    )
    return obj


# -------------------- WebSocket für Broadcast --------------------

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    # Client-Typ aus der URL lesen, z.B. ?client=picker oder ?client=bet
    client_type = ws.query_params.get("client", "unknown")
    print(f"WebSocket client connected: {client_type}")

    await manager.connect(ws)
    try:
        while True:
            msg = await ws.receive_text()
            # Wenn Clients später mal Nachrichten schicken:
            print(f"WS message from {client_type}: {msg}")
    except WebSocketDisconnect:
        print(f"WebSocket client disconnected: {client_type}")
        manager.disconnect(ws)


# -------------------- Spin-Result-Endpoint --------------------

@app.post("/spin-result", response_model=SpinResultOut)
async def save_spin_result(result: SpinResultIn, db: Session = Depends(get_db)):
    obj = SpinResult(
        tank1=result.tank1,
        tank2=result.tank2,
        dps1=result.dps1,
        dps2=result.dps2,
        support1=result.support1,
        support2=result.support2,
    )

    db.add(obj)
    db.commit()
    db.refresh(obj)

    # Optional: WebSocket Broadcast
    await manager.broadcast_json({
        "type": "spin_result",
        "id": obj.id,
        "created_at": obj.created_at.isoformat(),
        "tank1": obj.tank1,
        "tank2": obj.tank2,
        "dps1": obj.dps1,
        "dps2": obj.dps2,
        "support1": obj.support1,
        "support2": obj.support2,
    })

    return obj

@app.post("/roles-sync")
async def roles_sync(payload: RolesSyncIn, db: Session = Depends(get_db)):
    """
    Überschreibt die gespeicherten Namen je Rolle mit der übergebenen Liste.
    """
    total = 0

    for block in payload.roles:
        role = block.role
        names = block.names or []

        # Alte Einträge löschen
        db.query(RoleName).filter(RoleName.role == role).delete()

        # Neue Einträge speichern
        for idx, name in enumerate(names):
            db.add(RoleName(role=role, position=idx, name=name))
            total += 1

    db.commit()
    
    # Für WebSocket-Clients in ein einfaches JSON-Format bringen
    roles_json = [
        {"role": block.role, "names": block.names or []}
        for block in payload.roles
    ]

    # An alle verbundenen WebSocket-Clients senden
    await manager.broadcast_json({
        "type": "roles",
        "roles": roles_json,
    })
    
    return {"status": "ok", "roles": len(payload.roles), "entries": total}

# ganz oben:
from typing import Dict

# ...

@app.get("/roles-current", response_model=RolesSyncIn)
def roles_current(db: Session = Depends(get_db)):
    """
    Liefert die aktuell gespeicherten Namen je Rolle im gleichen Format
    wie /roles-sync (RolesSyncIn).
    """
    # Alle RoleName-Einträge holen, sortiert nach Rolle & Position
    rows = (
        db.query(RoleName)
        .order_by(RoleName.role.asc(), RoleName.position.asc())
        .all()
    )

    # in Dict role -> [names] einsortieren
    roles_map: Dict[str, list[str]] = {}
    for r in rows:
        roles_map.setdefault(r.role, []).append(r.name)

    # in das bekannte response-Format übersetzen
    payload = {
        "roles": [
            {"role": role, "names": names}
            for role, names in roles_map.items()
        ]
    }
    return payload

@app.get("/", response_class=HTMLResponse)
def spin_results_view(limit: int = 30, db: Session = Depends(get_db)):
    results = (
        db.query(SpinResult)
        .order_by(SpinResult.created_at.desc())
        .limit(limit)
        .all()
    )

    rows = ""
    counter = 1
    for r in results:
        rows += f"""
        <tr>
            <td>{counter}</td>
            <td>{r.created_at}</td>
            <td>{r.tank1}</td>
            <td>{r.tank2}</td>
            <td>{r.dps1}</td>
            <td>{r.dps2}</td>
            <td>{r.support1}</td>
            <td>{r.support2}</td>
        </tr>
        """
        counter += 1

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8"/>
        <title>Letzte Spins</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                background: #111;
                color: #eee;
                padding: 20px;
            }}
            h1 {{
                margin-bottom: 10px;
            }}
            table {{
                border-collapse: collapse;
                width: 100%;
                background: #1b1b1b;
            }}
            th, td {{
                border: 1px solid #444;
                padding: 8px 12px;
                text-align: left;
            }}
            th {{
                background: #222;
            }}
            tr:nth-child(even) {{
                background: #161616;
            }}
        </style>
    </head>
    <body>
        <h1>Letzte {limit} Spins</h1>
        <table>
            <thead>
                <tr>
                    <th>Nr.</th>
                    <th>Zeitpunkt</th>
                    <th>Tank1</th>
                    <th>Tank2</th>
                    <th>DPS 1</th>
                    <th>DPS 2</th>
                    <th>Support 1</th>
                    <th>Support 2</th>
                </tr>
            </thead>
            <tbody>
                {rows}
            </tbody>
        </table>
    </body>
    </html>
    """

    return html


# --------------------------------------------------------------------
# Tabellen erzeugen (nachdem ALLE Models definiert sind!)
# --------------------------------------------------------------------

Base.metadata.create_all(bind=engine)

def _on_ws_message(self, data: dict):
    if data.get("type") == "roles":
        self.model.set_roles(data["roles"])
