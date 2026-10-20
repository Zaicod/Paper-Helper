package cn.paperflow.mapper;

import cn.paperflow.entity.CollectionPaper;
import org.apache.ibatis.annotations.*;
import java.util.List;
import java.util.Optional;

@Mapper
public interface CollectionPaperMapper {
    @Select("SELECT COUNT(*) FROM pf_collection_papers WHERE collection_id = #{collectionId}")
    long countByCollectionId(@Param("collectionId") long collectionId);

    @Select("SELECT * FROM pf_collection_papers WHERE collection_id = #{collectionId} ORDER BY added_at ASC, id ASC")
    List<CollectionPaper> findByCollectionId(@Param("collectionId") long collectionId);

    @Select("SELECT * FROM pf_collection_papers WHERE collection_id = #{collectionId} AND paper_id = #{paperId}")
    Optional<CollectionPaper> findByCollectionIdAndPaperId(@Param("collectionId") long collectionId, @Param("paperId") long paperId);

    @Insert("INSERT INTO pf_collection_papers(collection_id, paper_id, note, added_at) VALUES(#{collectionId}, #{paperId}, #{note}, #{addedAt})")
    @Options(useGeneratedKeys = true, keyProperty = "id")
    int insert(CollectionPaper membership);

    @Update("UPDATE pf_collection_papers SET note = #{note} WHERE id = #{id} AND collection_id = #{collectionId}")
    int updateNote(CollectionPaper membership);

    @Update("UPDATE pf_collection_papers SET metadata_json = #{metadataJson}, metadata_edited = #{metadataEdited} WHERE id = #{id} AND collection_id = #{collectionId} AND paper_id = #{paperId}")
    int updateMetadata(CollectionPaper membership);

    @Delete("DELETE FROM pf_collection_papers WHERE id = #{id} AND collection_id = #{collectionId}")
    int delete(CollectionPaper membership);

    @Delete("DELETE FROM pf_collection_papers WHERE collection_id = #{collectionId}")
    int deleteAllForCollection(@Param("collectionId") long collectionId);
}
