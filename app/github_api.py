import asyncio, os, shutil, tempfile
from pathlib import Path
import httpx
class GitHubError(RuntimeError): pass
class GitHubClient:
    def __init__(self, token):
        self.token=token; self.http=httpx.AsyncClient(base_url="https://api.github.com",headers={"Authorization":"Bearer "+token,"Accept":"application/vnd.github+json","X-GitHub-Api-Version":"2022-11-28","User-Agent":"tg-builder-v2"},timeout=90,follow_redirects=True)
    async def close(self): await self.http.aclose()
    async def req(self,method,url,**kwargs):
        r=await self.http.request(method,url,**kwargs)
        if r.status_code>=400:
            try: msg=r.json().get("message",r.text[:400])
            except Exception: msg=r.text[:400]
            raise GitHubError(f"GitHub {r.status_code}: {msg}")
        return r
    async def whoami(self): return (await self.req("GET","/user")).json()["login"]
    async def create_repo(self,name):
        d=(await self.req("POST","/user/repos",json={"name":name,"private":True,"auto_init":False,"has_issues":False,"has_projects":False,"has_wiki":False})).json(); return d["full_name"]
    async def push(self,directory: Path,repo: str):
        remote="https://github.com/"+repo+".git"; temp=Path(tempfile.mkdtemp(prefix="askpass-")); ask=temp/"ask.sh"
        ask.write_text('#!/bin/sh\ncase "$1" in *Username*) echo "x-access-token";; *) echo "$GH_PAT";; esac\n'); ask.chmod(0o700)
        env=os.environ.copy(); env.update({"GIT_ASKPASS":str(ask),"GIT_TERMINAL_PROMPT":"0","GH_PAT":self.token})
        async def run(*args):
            p=await asyncio.create_subprocess_exec("git",*args,cwd=directory,env=env,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE); out,err=await p.communicate()
            if p.returncode: raise GitHubError("git: "+(err or out).decode(errors="replace")[-1400:].replace(self.token,"***"))
        try:
            for cmd in (("init","-b","main"),("config","user.name","Telegram Builder"),("config","user.email","builder@users.noreply.github.com"),("add","--all"),("commit","-m","Build upload"),("remote","add","origin",remote),("push","-u","origin","main")): await run(*cmd)
        finally: shutil.rmtree(temp,ignore_errors=True)
    async def wait_run(self,repo,timeout=180):
        for _ in range(timeout//5):
            d=(await self.req("GET",f"/repos/{repo}/actions/runs",params={"event":"push","branch":"main","per_page":5})).json()
            if d.get("workflow_runs"): return int(d["workflow_runs"][0]["id"])
            await asyncio.sleep(5)
        raise GitHubError("GitHub Actions не запустился")
    async def wait_done(self,repo,run_id,timeout=2500):
        for _ in range(timeout//10):
            d=(await self.req("GET",f"/repos/{repo}/actions/runs/{run_id}")).json()
            if d["status"]=="completed": return d.get("conclusion") or "unknown"
            await asyncio.sleep(10)
        raise GitHubError("Превышено время сборки")
    async def artifact(self,repo,run_id,dst: Path):
        d=(await self.req("GET",f"/repos/{repo}/actions/runs/{run_id}/artifacts")).json(); items=[x for x in d.get("artifacts",[]) if not x.get("expired")]
        if not items: raise GitHubError("GitHub не создал артефакт")
        dst.write_bytes((await self.req("GET",items[0]["archive_download_url"])).content); return dst
    async def delete_repo(self,repo): await self.req("DELETE",f"/repos/{repo}")
