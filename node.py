#!/usr/bin/env python3
"""NRB Docker Node Agent.
Remote nodes run Docker containers only; no Docker runtime installation is required.
"""
import os, subprocess, platform, shutil
from flask import Flask, jsonify, request

app=Flask(__name__)
API_KEY=os.getenv('NRB_NODE_API_KEY','')
PORT=int(os.getenv('PORT','9000'))

def auth():
    return (not API_KEY) or request.headers.get('X-API-Key')==API_KEY

def run(cmd, timeout=120):
    p=subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
    return p.returncode,p.stdout,p.stderr

@app.get('/api/info')
def info():
    if not auth(): return jsonify(success=False,error='Unauthorized'),401
    return jsonify(success=True, version='NRB Docker Node 1.0', python_version=platform.python_version(), docker=shutil.which('docker') or 'not-found')

@app.post('/api/execute')
def execute():
    if not auth(): return jsonify(success=False,error='Unauthorized'),401
    data=request.get_json(silent=True) or {}
    command=str(data.get('command','')).strip()
    timeout=int(data.get('timeout',120))
    if not command.startswith('docker '):
        return jsonify(success=False,error='Only Docker commands are allowed'),400
    try:
        code,out,err=run(command,timeout)
        return jsonify(success=code==0,stdout=out,stderr=err,returncode=code)
    except Exception as e:
        return jsonify(success=False,error=str(e)),500

@app.get('/api/status')
def status():
    if not auth(): return jsonify(success=False,error='Unauthorized'),401
    code,out,err=run('docker info --format "{{.ServerVersion}}"',10)
    return jsonify(success=code==0, docker_version=out.strip() if code==0 else None, error=err.strip() if code else None)

@app.post('/api/container/<action>')
def container_action(action):
    if not auth(): return jsonify(success=False,error='Unauthorized'),401
    if action not in {'start','stop','restart','pause','unpause'}: return jsonify(success=False,error='Invalid action'),400
    name=(request.get_json(silent=True) or {}).get('container','')
    if not name: return jsonify(success=False,error='Container required'),400
    code,out,err=run(f'docker {action} {name}',120)
    return jsonify(success=code==0,stdout=out,stderr=err)

if __name__=='__main__':
    app.run(host='0.0.0.0',port=PORT)
