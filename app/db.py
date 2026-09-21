import aiosqlite
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Upload:
    id: str
    user_id: int
    filename: str
    path: str
    size: int
    sha256: str


class Database:
    def __init__(self, path: Path): self.path = path

    async def init(self):
        async with aiosqlite.connect(self.path) as db:
            await db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS github_accounts(
              user_id INTEGER PRIMARY KEY, username TEXT NOT NULL,
              encrypted_token TEXT NOT NULL, updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS uploads(
              id TEXT PRIMARY KEY, user_id INTEGER NOT NULL, filename TEXT NOT NULL,
              path TEXT NOT NULL, size INTEGER NOT NULL, sha256 TEXT NOT NULL,
              created_at TEXT DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS builds(
              id TEXT PRIMARY KEY, user_id INTEGER NOT NULL, upload_id TEXT NOT NULL,
              mode TEXT NOT NULL, status TEXT NOT NULL, detected_type TEXT,
              repository TEXT, run_id INTEGER, error TEXT,
              created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
            """)
            columns = {row[1] for row in await (await db.execute("PRAGMA table_info(builds)")).fetchall()}
            if "mode" not in columns:
                await db.execute("ALTER TABLE builds ADD COLUMN mode TEXT")
                if "kind" in columns:
                    await db.execute("UPDATE builds SET mode=kind WHERE mode IS NULL")
            if "detected_type" not in columns:
                await db.execute("ALTER TABLE builds ADD COLUMN detected_type TEXT")
            await db.commit()

    async def save_account(self, uid, username, encrypted):
        async with aiosqlite.connect(self.path) as db:
            await db.execute("INSERT INTO github_accounts(user_id,username,encrypted_token) VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET username=excluded.username,encrypted_token=excluded.encrypted_token,updated_at=CURRENT_TIMESTAMP", (uid, username, encrypted)); await db.commit()

    async def get_account(self, uid):
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute("SELECT username,encrypted_token FROM github_accounts WHERE user_id=?", (uid,)); return await cur.fetchone()

    async def delete_account(self, uid):
        async with aiosqlite.connect(self.path) as db:
            await db.execute("DELETE FROM github_accounts WHERE user_id=?", (uid,)); await db.commit()

    async def save_upload(self, up: Upload):
        async with aiosqlite.connect(self.path) as db:
            await db.execute("INSERT INTO uploads(id,user_id,filename,path,size,sha256) VALUES(?,?,?,?,?,?)", (up.id,up.user_id,up.filename,up.path,up.size,up.sha256)); await db.commit()

    async def get_upload(self, upload_id, uid):
        async with aiosqlite.connect(self.path) as db:
            cur=await db.execute("SELECT id,user_id,filename,path,size,sha256 FROM uploads WHERE id=? AND user_id=?",(upload_id,uid)); row=await cur.fetchone(); return Upload(*row) if row else None

    async def create_build(self, bid, uid, upload_id, mode):
        async with aiosqlite.connect(self.path) as db:
            await db.execute("INSERT INTO builds(id,user_id,upload_id,mode,status) VALUES(?,?,?,?,?)",(bid,uid,upload_id,mode,"preparing")); await db.commit()

    async def update_build(self, bid, *, status, detected_type=None, repository=None, run_id=None, error=None):
        fields=["status=?","updated_at=CURRENT_TIMESTAMP"]; values=[status]
        for name,value in (("detected_type",detected_type),("repository",repository),("run_id",run_id),("error",error)):
            if value is not None: fields.append(name+"=?"); values.append(value)
        values.append(bid)
        async with aiosqlite.connect(self.path) as db:
            await db.execute("UPDATE builds SET "+",".join(fields)+" WHERE id=?",values); await db.commit()

    async def recent_builds(self, uid, limit=8):
        async with aiosqlite.connect(self.path) as db:
            cur=await db.execute("SELECT id,mode,status,detected_type,repository,created_at FROM builds WHERE user_id=? ORDER BY created_at DESC LIMIT ?",(uid,limit)); return await cur.fetchall()
