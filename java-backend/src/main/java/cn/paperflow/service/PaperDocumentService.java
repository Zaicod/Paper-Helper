package cn.paperflow.service;
import cn.paperflow.client.WorkerClient;
import cn.paperflow.common.ApiException;
import cn.paperflow.entity.PaperDocumentRegistration;
import cn.paperflow.mapper.PaperDocumentMapper;
import cn.paperflow.vo.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import java.util.*;
import java.time.Instant;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;

/** Remote preparation is outside transactions; immutable registrations survive library edits. */
@Service
public class PaperDocumentService {
 private final LibraryService library;private final PaperDocumentMapper rows;private final WorkerClient worker;private final ObjectMapper json;
 public PaperDocumentService(LibraryService library,PaperDocumentMapper rows,WorkerClient worker,ObjectMapper json){this.library=library;this.rows=rows;this.worker=worker;this.json=json;}
 public static Map<String,Object> snapshot(PaperVO p){
  Map<String,Object> m=new LinkedHashMap<>();m.put("source",p.source());m.put("paper_id",p.paperId());m.put("title",p.title());m.put("abstract",p.abstractText());m.put("authors",p.authors());m.put("categories",p.categories());m.put("published",p.published());m.put("page_url",p.pageUrl());m.put("pdf_url",p.pdfUrl());return m;
 }
 private String encode(Object value){try{return json.writeValueAsString(value);}catch(Exception e){throw new IllegalStateException("Document serialization failed");}}
 private String hash(PaperVO p){try{return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(encode(snapshot(p)).getBytes(StandardCharsets.UTF_8)));}catch(Exception e){throw new IllegalStateException("Document hashing failed");}}
 private PaperDocumentVO decode(String value){try{return json.readValue(value,PaperDocumentVO.class);}catch(Exception e){throw new IllegalStateException("Document record invalid");}}
 private PaperDocumentVO unprepared(){return new PaperDocumentVO(null,"not_prepared","请先准备正文或上传已有 PDF，再创建全文学习报告。",null,null,null,null,null);}
 public PaperDocumentVO status(long owner,long collection,long paper){return status(owner,collection,library.paper(owner,collection,paper));}
 private PaperDocumentVO status(long owner,long collection,PaperVO p){var row=rows.latest(owner,collection,p.id());return row!=null&&hash(p).equals(row.metadataHash())?decode(row.statusJson()):unprepared();}
 public PaperDocumentVO prepare(long owner,long collection,long paper,byte[] file,String filename){
  var p=library.paper(owner,collection,paper);String before=hash(p);
  if(file==null){var old=status(owner,collection,p);if("ready".equals(old.status()))return old;}
  try{
   String namespace="java-user:"+owner;
   String upload=file==null?null:worker.uploadDocument(namespace,filename,file);
   var value=worker.prepareDocument(namespace,snapshot(p),upload);
   if(!before.equals(hash(library.paper(owner,collection,paper))))throw new ApiException(HttpStatus.CONFLICT,"论文资料已变化，请重新准备正文");
   rows.insert(new PaperDocumentRegistration(UUID.randomUUID().toString(),owner,collection,paper,before,value.documentId(),encode(value),Instant.now()));return value;
  }catch(InterruptedException e){Thread.currentThread().interrupt();throw new ApiException(HttpStatus.SERVICE_UNAVAILABLE,"正文准备已中断，请重试");}
   catch(java.io.IOException e){throw new ApiException(HttpStatus.BAD_GATEWAY,"正文准备服务暂时不可用，请稍后重试");}
 }
 public Map<String,String> requireReady(long owner,long collection,List<PaperVO> papers){
  Map<String,String> result=new LinkedHashMap<>();for(var p:papers){var value=status(owner,collection,p);if(!"ready".equals(value.status())||value.documentId()==null)throw new ApiException(HttpStatus.CONFLICT,"论文「"+p.title().substring(0,Math.min(120,p.title().length()))+"」的正文尚未准备，请先准备或上传 PDF");result.put(p.paperId(),value.documentId());}return result;
 }
 public byte[] download(long owner,String id){
  if(rows.document(owner,id)==null)throw new ApiException(HttpStatus.NOT_FOUND,"正文文件不存在");
  try{return worker.documentFile("java-user:"+owner,id);}
  catch(InterruptedException e){Thread.currentThread().interrupt();throw new ApiException(HttpStatus.SERVICE_UNAVAILABLE,"下载已中断");}
  catch(java.io.IOException e){throw new ApiException(HttpStatus.BAD_GATEWAY,"正文文件暂时无法读取");}
 }
}
