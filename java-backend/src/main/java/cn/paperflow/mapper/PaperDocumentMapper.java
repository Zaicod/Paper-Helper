package cn.paperflow.mapper;
import cn.paperflow.entity.PaperDocumentRegistration;
import org.apache.ibatis.annotations.*;
@Mapper
public interface PaperDocumentMapper {
 @Select("SELECT * FROM pf_paper_documents WHERE owner_id=#{owner} AND collection_id=#{collection} AND paper_id=#{paper} ORDER BY created_at DESC,record_id DESC LIMIT 1")
 PaperDocumentRegistration latest(@Param("owner") long owner,@Param("collection") long collection,@Param("paper") long paper);
 @Select("SELECT * FROM pf_paper_documents WHERE owner_id=#{owner} AND document_id=#{document} ORDER BY created_at DESC LIMIT 1")
 PaperDocumentRegistration document(@Param("owner") long owner,@Param("document") String document);
 @Insert("INSERT INTO pf_paper_documents(record_id,owner_id,collection_id,paper_id,metadata_hash,document_id,status_json,created_at) VALUES(#{recordId},#{ownerId},#{collectionId},#{paperId},#{metadataHash},#{documentId},#{statusJson},#{createdAt})")
 int insert(PaperDocumentRegistration row);
}
