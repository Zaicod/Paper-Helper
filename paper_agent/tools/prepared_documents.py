"""Immutable, namespace-private PDF files and extracted preparation snapshots."""
from __future__ import annotations
import asyncio
import hashlib
import json
import os
from pathlib import Path
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit, unquote
from uuid import UUID, uuid4
import httpx
from paper_agent.core.models import EvidenceChunk, Paper
from paper_agent.tools.study_pdf import MAX_PDF_BYTES, _fetch_public_pdf, _extract_pdf


def fingerprint(paper):
    return hashlib.sha256(json.dumps(Paper.model_validate(paper).model_dump(mode='json'),
        ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def _namespace(value):
    if not isinstance(value,str) or not re.fullmatch(r'java-user:[1-9]\d{0,18}',value):
        raise ValueError('Invalid document namespace')
    return value


def _identifier(value):
    try:return str(UUID(str(value)))
    except (ValueError,TypeError,AttributeError):raise ValueError('Invalid document identifier') from None


async def resolve_open_pdf_candidates(paper,*,transport=None):
    """Only fixed OpenAlex metadata, matched by DOI and/or exact OpenAlex ID."""
    url=urlsplit(paper.page_url)
    doi=unquote(url.path).lstrip('/') if url.hostname in ('doi.org','dx.doi.org') else ''
    if not re.fullmatch(r'10\.\d{4,9}/\S+',doi,re.I):doi=''
    if not doi and paper.source=='crossref' and re.fullmatch(r'10\.\d{4,9}/\S+',paper.paper_id,re.I):doi=paper.paper_id
    if doi.lower().startswith('10.48550/arxiv.'):
        arxiv=doi[len('10.48550/arxiv.'):]
        if re.fullmatch(r'(?:\d{4}\.\d{4,5}|[a-z-]+/\d{7})(?:v\d+)?',arxiv,re.I):return ['https://arxiv.org/pdf/'+arxiv]
    if paper.source=='arxiv' and re.fullmatch(r'(?:\d{4}\.\d{4,5}|[a-z-]+/\d{7})(?:v\d+)?',paper.paper_id,re.I):
        return ['https://arxiv.org/pdf/'+paper.paper_id]
    work_id=paper.paper_id if paper.source=='openalex' and re.fullmatch(r'W\d+',paper.paper_id) else None
    if not work_id and not doi:return []
    lookup=work_id or 'https://doi.org/'+doi
    params={}
    if os.getenv('OPENALEX_API_KEY'):params['api_key']=os.environ['OPENALEX_API_KEY']
    async with httpx.AsyncClient(timeout=8,follow_redirects=False,transport=transport) as client:
        response=await client.get('https://api.openalex.org/works/'+lookup,params=params)
        response.raise_for_status();item=response.json()
    if not isinstance(item,dict):return []
    if work_id and item.get('id','').rstrip('/').split('/')[-1]!=work_id:return []
    if doi and str(item.get('doi','')).lower().removeprefix('https://doi.org/').removeprefix('http://doi.org/')!=doi.lower():return []
    locations=[item.get('best_oa_location'),item.get('primary_location'),*(item.get('locations') or [])]
    urls=[]
    for location in locations:
        if not isinstance(location,dict) or location.get('is_oa') is not True:continue
        candidate=location.get('pdf_url')
        if isinstance(candidate,str) and len(candidate)<=2048 and candidate.startswith('https://') and candidate not in urls:
            urls.append(candidate)
    return urls[:3]


class PreparedDocumentStore:
    def __init__(self,root,*,resolver=None,fetcher=None,extractor=None):
        self.root=Path(root).resolve();self.root.mkdir(parents=True,exist_ok=True)
        self.resolver=resolver or resolve_open_pdf_candidates
        self.fetcher=fetcher or _fetch_public_pdf
        self.extractor=extractor or _extract_pdf

    def _path(self,identifier,suffix):return self.root/(_identifier(identifier)+suffix)

    def _write_json(self,path,value):
        temporary=path.with_name(path.name+'.'+uuid4().hex+'.tmp')
        try:
            temporary.write_text(json.dumps(value,ensure_ascii=False),encoding='utf8')
            os.replace(temporary,path)
        finally:temporary.unlink(missing_ok=True)

    def _read(self,namespace,identifier,upload=False):
        _namespace(namespace)
        try:metadata=json.loads(self._path(identifier,'.upload.json' if upload else '.json').read_text(encoding='utf8'))
        except (OSError,ValueError):raise ValueError('Document is unavailable') from None
        if metadata.get('namespace')!=namespace:raise ValueError('Document is unavailable')
        return metadata

    async def upload(self,namespace,filename,content):
        _namespace(namespace)
        if not isinstance(content,bytes) or len(content)>MAX_PDF_BYTES or not content.lstrip().startswith(b'%PDF-'):
            raise ValueError('Only PDF files up to 25 MiB are supported')
        filename=Path(str(filename).replace('\\','/')).name
        filename=''.join(c for c in filename if ord(c)>=32)[:255] or 'document.pdf'
        digest=hashlib.sha256(content).hexdigest()
        pointer=self.root/('upload-'+hashlib.sha256((namespace+':'+digest).encode()).hexdigest()+'.json')
        if pointer.exists():
            try:
                identifier=json.loads(pointer.read_text(encoding='utf8'))['id']
                metadata=self._read(namespace,identifier,True)
                if metadata['sha256']==digest and self._path(identifier,'.upload.pdf').exists():return identifier
            except (ValueError,KeyError,OSError):pass
        identifier=str(uuid4())
        self._path(identifier,'.upload.pdf').write_bytes(content)
        self._write_json(self._path(identifier,'.upload.json'),{'namespace':namespace,'filename':filename,
            'sha256':digest})
        self._write_json(pointer,{'id':identifier})
        return identifier

    def _status(self,status,message,**extra):
        return dict(document_id=None,status=status,message=message,filename=None,sha256=None,
            source_kind=None,page_count=None,prepared_at=None,**extra)

    async def prepare(self,namespace,paper,upload_id=None):
        _namespace(namespace);paper=Paper.model_validate(paper)
        uploaded=self._read(namespace,upload_id,True) if upload_id else None
        pointer=None
        if uploaded:
            key=hashlib.sha256((namespace+':'+fingerprint(paper)+':'+uploaded['sha256']).encode()).hexdigest()
            pointer=self.root/('prepared-'+key+'.json')
            if pointer.exists():
                try:
                    identifier=json.loads(pointer.read_text(encoding='utf8'))['id']
                    await self.read_pdf(namespace,identifier)
                    return self._read(namespace,identifier)['status']
                except (ValueError,KeyError,OSError):pass
        try:
            async with asyncio.timeout(120):
                if uploaded:
                    content=self._path(upload_id,'.upload.pdf').read_bytes()
                    if hashlib.sha256(content).hexdigest()!=uploaded['sha256']:raise ValueError('Invalid upload')
                    result=await self._publish(namespace,paper,content,None,'uploaded',uploaded['filename'])
                    self._write_json(pointer,{'id':result['document_id']})
                    return result
                candidates=[paper.pdf_url] if paper.pdf_url else []
                if candidates:
                    try:
                        content,source=await asyncio.to_thread(self.fetcher,self._https(candidates[0]))
                        return await self._publish(namespace,paper,content,source,'remote','document.pdf')
                    except Exception as exc:first_error=self._failure(exc)
                else:first_error=None
                try:resolved=await self.resolver(paper)
                except Exception:
                    return first_error or self._status('unavailable','暂时无法查询公开正文位置，请稍后重试或上传已有 PDF。')
                for url in resolved[:3]:
                    if url in candidates:continue
                    try:
                        content,source=await asyncio.to_thread(self.fetcher,self._https(url))
                        return await self._publish(namespace,paper,content,source,'remote','document.pdf')
                    except Exception as exc:first_error=self._failure(exc)
                return first_error or self._status('missing','没有找到可用的公开 PDF。请补充公开链接，或上传已有 PDF。')
        except TimeoutError:return self._status('timeout','正文准备超时，请稍后重试或上传已有 PDF。')
        except Exception as exc:return self._failure(exc)

    @staticmethod
    def _https(url):
        parts=urlsplit(url)
        if parts.scheme=='http' and parts.netloc.lower()=='arxiv.org' and parts.path.startswith('/pdf/'):
            return parts._replace(scheme='https').geturl()
        return url

    def _failure(self,exc):
        if isinstance(exc,(TimeoutError,httpx.TimeoutException)):return self._status('timeout','正文下载或解析超时，请重试或上传已有 PDF。')
        if isinstance(exc,(OSError,httpx.HTTPError)):return self._status('unavailable','正文来源暂时无法访问，请重试或上传已有 PDF。')
        code=getattr(exc,'preparation_status',None)
        if code=='blocked':return self._status('blocked','正文来源要求登录、验证或拒绝访问，请上传已获取的 PDF。')
        if code=='unavailable':return self._status('unavailable','正文来源暂时无法提供 PDF，请稍后重试或上传已有文件。')
        return self._status('unreadable','文件无法提取足够文本，可能是扫描件、加密文件或非 PDF 页面；请上传可提取文本的 PDF。')

    async def _publish(self,namespace,paper,content,source,kind,filename):
        if len(content)>MAX_PDF_BYTES or not content.lstrip().startswith(b'%PDF-'):raise ValueError('Invalid PDF')
        identifier=str(uuid4())
        source=source or '/api/library/documents/'+identifier+'/file'
        chunks=await asyncio.to_thread(self.extractor,content,paper,source)
        if not chunks or any(c.paper_id!=paper.paper_id or not c.page_number for c in chunks):raise ValueError('Invalid PDF evidence')
        digest=hashlib.sha256(content).hexdigest();stamp=datetime.now(timezone.utc).isoformat()
        status={'document_id':identifier,'status':'ready','message':'正文已准备，可创建全文学习报告。',
            'filename':filename,'sha256':digest,'source_kind':kind,'page_count':max(c.page_number for c in chunks),'prepared_at':stamp}
        self._path(identifier,'.pdf').write_bytes(content)
        self._write_json(self._path(identifier,'.json'),{'namespace':namespace,'paper_fingerprint':fingerprint(paper),
            'status':status,'chunks':[c.model_dump(mode='json') for c in chunks]})
        return status

    async def read_pdf(self,namespace,identifier):
        record=self._read(namespace,identifier)
        content=self._path(identifier,'.pdf').read_bytes()
        if len(content)>MAX_PDF_BYTES or hashlib.sha256(content).hexdigest()!=record['status']['sha256']:
            raise ValueError('Document is unavailable')
        return content

    async def load(self,namespace,identifier,paper):
        record=self._read(namespace,identifier)
        if record['paper_fingerprint']!=fingerprint(paper):raise ValueError('Prepared paper snapshot changed')
        await self.read_pdf(namespace,identifier)
        return [EvidenceChunk.model_validate(c) for c in record['chunks']]


class PreparedPDFLoader:
    def __init__(self,store,namespace,documents):self.store,self.namespace,self.documents=store,namespace,documents
    async def load(self,paper):
        identifier=self.documents.get(paper.paper_id)
        if not identifier:raise ValueError('Paper has no prepared document snapshot')
        return await self.store.load(self.namespace,identifier,paper)
    def recipe_for(self,paper):
        identifier=self.documents.get(paper.paper_id)
        if not identifier:raise ValueError('Paper has no prepared document snapshot')
        return 'prepared-'+_identifier(identifier)
