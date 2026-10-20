package cn.paperflow.mapper;

import cn.paperflow.entity.Paper;
import org.apache.ibatis.annotations.*;
import java.util.List;
import java.util.Optional;

@Mapper
public interface PaperMapper {
    @Select("SELECT * FROM pf_papers WHERE source = #{source} AND external_id = #{externalId}")
    Optional<Paper> findBySourceAndExternalId(@Param("source") String source, @Param("externalId") String externalId);

    @Select("<script>SELECT * FROM pf_papers WHERE id IN <foreach collection='ids' item='id' open='(' separator=',' close=')'>#{id}</foreach></script>")
    List<Paper> findAllById(@Param("ids") List<Long> ids);

    @Insert("INSERT INTO pf_papers(source, external_id, title, abstract_text, authors_json, categories_json, published, page_url, pdf_url, created_at) VALUES(#{source}, #{externalId}, #{title}, #{abstractText}, #{authorsJson}, #{categoriesJson}, #{published}, #{pageUrl}, #{pdfUrl}, #{createdAt})")
    @Options(useGeneratedKeys = true, keyProperty = "id")
    int insert(Paper paper);
}
