package cn.paperflow.mapper;

import cn.paperflow.entity.PaperCollection;
import org.apache.ibatis.annotations.*;
import java.util.List;
import java.util.Optional;

@Mapper
public interface CollectionMapper {
    String FILTER = "owner_id = #{owner} AND (#{query} = '' OR LOWER(name) LIKE LOWER(CONCAT('%', #{query}, '%')) OR LOWER(description) LIKE LOWER(CONCAT('%', #{query}, '%')))";

    @Select("SELECT * FROM pf_collections WHERE id = #{id} AND owner_id = #{owner}")
    Optional<PaperCollection> findOwned(@Param("owner") long owner, @Param("id") long id);

    @Select("SELECT COUNT(*) FROM pf_collections WHERE owner_id = #{owner} AND name_normalized = #{name} AND id <> #{excluded}")
    long countSameName(@Param("owner") long owner, @Param("name") String name, @Param("excluded") long excluded);

    @Select("SELECT * FROM pf_collections WHERE " + FILTER + " ORDER BY created_at DESC, id DESC LIMIT #{size} OFFSET #{offset}")
    List<PaperCollection> searchOwned(@Param("owner") long owner, @Param("query") String query, @Param("offset") long offset, @Param("size") int size);

    @Select("SELECT COUNT(*) FROM pf_collections WHERE " + FILTER)
    long countOwned(@Param("owner") long owner, @Param("query") String query);

    @Insert("INSERT INTO pf_collections(owner_id, name, name_normalized, description, overall_note, created_at) VALUES(#{ownerId}, #{name}, #{nameNormalized}, #{description}, #{overallNote}, #{createdAt})")
    @Options(useGeneratedKeys = true, keyProperty = "id")
    int insert(PaperCollection collection);

    @Update("UPDATE pf_collections SET name = #{name}, name_normalized = #{nameNormalized}, description = #{description} WHERE id = #{id} AND owner_id = #{ownerId}")
    int update(PaperCollection collection);

    @Update("UPDATE pf_collections SET overall_note = #{content} WHERE id = #{id} AND owner_id = #{owner}")
    int updateNote(@Param("owner") long owner, @Param("id") long id, @Param("content") String content);

    @Delete("DELETE FROM pf_collections WHERE id = #{id} AND owner_id = #{owner}")
    int delete(@Param("owner") long owner, @Param("id") long id);
}
