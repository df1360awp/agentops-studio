"""Optional OpenAI-compatible model adapter. Never called unless user opts in."""
from __future__ import annotations
import json
import os
import urllib.error
import urllib.request


def settings():
    return {
        'configured': bool(os.getenv('OPENAI_COMPAT_API_KEY') or os.getenv('OPENAI_API_KEY')),
        'model': os.getenv('OPENAI_COMPAT_MODEL','gpt-4o-mini'),
        'base_url': os.getenv('OPENAI_COMPAT_BASE_URL','https://api.openai.com/v1')
    }


def complete(question,context):
    s=settings()
    key=os.getenv('OPENAI_COMPAT_API_KEY') or os.getenv('OPENAI_API_KEY')
    if not key:
        raise RuntimeError('未设置 OPENAI_COMPAT_API_KEY。请使用离线规则模式，或在本地环境变量中配置兼容接口。')
    url=s['base_url'].rstrip('/')+'/chat/completions'
    if not url.startswith('https://') and not (url.startswith('http://127.0.0.1:') or url.startswith('http://localhost:')):
        raise RuntimeError('模型接口必须使用HTTPS，或指向本机localhost。')
    system='''你是为运营数据辅助决策的工作流分析助手。所有输入来自用户主动导入的业务资料或明确启用的虚构示例。
必须只使用给定数据推导结论，不编造经营绩效、API结果、市场事件或未经核实的企业信息。
输出用简洁中文，优先引用输入记录ID，区分数据事实、规则建议和未经验证的推断。
涉及真实对客沟通、投放调价、达人合同等动作必须保留人工审批。不得声明已执行实际外部操作。'''
    data={
      'model':s['model'],
      'messages':[{'role':'system','content':system},{'role':'user','content':'业务数据摘要：\n'+json.dumps(context,ensure_ascii=False)[:12000]+'\n\n问题：'+question[:500]}],
      'temperature':0.2,'max_tokens':550
    }
    payload=json.dumps(data,ensure_ascii=False).encode('utf-8')
    req=urllib.request.Request(url,data=payload,headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'},method='POST')
    try:
        with urllib.request.urlopen(req,timeout=22) as resp:
            result=json.loads(resp.read(1024*1024))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f'模型API返回HTTP {e.code}，请检查模型名、额度或密钥。')
    except Exception as e:
        raise RuntimeError('模型连接失败：'+str(e)[:180])
    try:
        content=result['choices'][0]['message']['content']
        if not isinstance(content,str): raise ValueError('content not text')
        return content
    except (KeyError,IndexError,TypeError,ValueError):
        raise RuntimeError('模型接口返回格式不符合chat/completions规范。')
