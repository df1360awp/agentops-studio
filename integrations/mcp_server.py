"""Optional real MCP STDIO server for hosts supporting Model Context Protocol.
Requires `pip install mcp` and the local AgentOps FastAPI app running.
This adapter is supplied as source, not represented as having been deployed/verified with a host.
"""
import json
import os
import urllib.request
from mcp.server.fastmcp import FastMCP

API=os.environ.get('AGENTOPS_API_URL','http://127.0.0.1:8765')
TOKEN=os.environ.get('AGENTOPS_API_TOKEN','')
def headers():
    return {'Authorization':'Bearer '+TOKEN} if TOKEN else {}
mcp=FastMCP('agentops-studio')

def get(path):
    with urllib.request.urlopen(urllib.request.Request(API+path,headers=headers()),timeout=15) as r:
        return json.loads(r.read())

def post(path):
    req=urllib.request.Request(API+path,data=b'{}',headers={'Content-Type':'application/json',**headers()},method='POST')
    with urllib.request.urlopen(req,timeout=30) as r:
        return json.loads(r.read())

@mcp.tool()
def get_business_overview()->str:
    """Read imported (or explicitly seeded sample) DTC, ads and creator metrics."""
    return json.dumps(get('/api/overview'),ensure_ascii=False)

@mcp.tool()
def list_available_workflows()->str:
    """Read workflow IDs, purpose and node definitions."""
    return json.dumps(get('/api/workflows'),ensure_ascii=False)

@mcp.tool()
def run_review_workflow(workflow_id:str)->str:
    """Run local analysis workflow; cannot execute ads, messages or payouts."""
    if workflow_id not in ('voc','ads','kol','brief'):
        return 'Invalid workflow ID; use voc, ads, kol, or brief.'
    return json.dumps(post(f'/api/workflows/{workflow_id}/run'),ensure_ascii=False)

@mcp.tool()
def get_human_approvals()->str:
    """Read pending actions; this MCP server deliberately exposes no approval-write tool."""
    return json.dumps(get('/api/approvals'),ensure_ascii=False)

if __name__=='__main__':
    mcp.run(transport='stdio')
