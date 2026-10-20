package cn.paperflow.mapper;

import cn.paperflow.entity.ResearchTask;
import org.apache.ibatis.annotations.*;
import java.util.List;

@Mapper
public interface ResearchTaskMapper {
    @Select("SELECT id FROM pf_users WHERE id=#{owner} FOR UPDATE")
    Long lockOwner(long owner);
    @Select("SELECT * FROM pf_research_tasks WHERE owner_id=#{owner} AND idempotency_key=#{key}")
    ResearchTask findRequest(@Param("owner") long owner,@Param("key") String key);
    @Select("SELECT * FROM pf_research_tasks WHERE task_id=#{id} AND owner_id=#{owner}")
    ResearchTask findOwned(@Param("id") String id,@Param("owner") long owner);
    @Select("""
        SELECT COUNT(*) FROM pf_collection_papers cp
        JOIN pf_collections c ON c.id=cp.collection_id
        JOIN pf_papers p ON p.id=cp.paper_id
        WHERE c.owner_id=#{owner} AND p.source=#{source} AND p.external_id=#{paperId}
        """)
    long countOwnedPaper(@Param("owner") long owner,@Param("source") String source,@Param("paperId") String paperId);
    @Select("SELECT * FROM pf_research_tasks WHERE task_id=#{id}")
    ResearchTask findById(String id);
    String OWNED_FILTER = """
        WHERE owner_id=#{owner}
        <if test="states != null">
          AND status IN <foreach collection="states" item="state" open="(" separator="," close=")">#{state}</foreach>
        </if>
        <if test="keyword != null">AND LOWER(topic) LIKE #{keyword} ESCAPE '!'</if>
        """;
    @Select("<script>SELECT * FROM pf_research_tasks " + OWNED_FILTER +
        " ORDER BY created_at DESC,task_id DESC LIMIT #{size} OFFSET #{offset}</script>")
    List<ResearchTask> listOwned(@Param("owner") long owner,@Param("offset") long offset,@Param("size") int size,
        @Param("states") List<String> states,@Param("keyword") String keyword);
    @Select("<script>SELECT COUNT(*) FROM pf_research_tasks " + OWNED_FILTER + "</script>")
    long countOwned(@Param("owner") long owner,@Param("states") List<String> states,@Param("keyword") String keyword);
    @Select("SELECT * FROM pf_research_tasks WHERE status IN ('queued','running') ORDER BY updated_at,task_id LIMIT 50")
    List<ResearchTask> pending();
    @Insert("""
        INSERT INTO pf_research_tasks(task_id,owner_id,idempotency_key,request_hash,topic,status,payload_json,
          events_json,created_at,updated_at,deadline_at,version)
        VALUES(#{taskId},#{ownerId},#{idempotencyKey},#{requestHash},#{topic},#{status},#{payloadJson},
          #{eventsJson},#{createdAt},#{updatedAt},#{deadlineAt},0)
        """)
    int insert(ResearchTask task);
    @Update("""
        UPDATE pf_research_tasks SET status=#{status},events_json=#{eventsJson},report_json=#{reportJson},
          error_code=#{errorCode},error_message=#{errorMessage},sync_error=#{syncError},updated_at=#{updatedAt},version=version+1
        WHERE task_id=#{taskId} AND version=#{version} AND status IN ('queued','running')
        """)
    int update(ResearchTask task);
}
