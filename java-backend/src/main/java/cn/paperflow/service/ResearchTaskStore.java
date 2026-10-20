package cn.paperflow.service;

import com.fasterxml.jackson.databind.JsonNode;
import java.time.Instant;
import java.util.List;

/** 后台同步使用的短事务接口，网络调用放在事务外。 */
public interface ResearchTaskStore {
    record Pending(String taskId,String status,String payload,Instant deadline,long ownerId) {
        public Pending(String taskId,String status,String payload,Instant deadline){this(taskId,status,payload,deadline,0);}
    }
    List<Pending> pending();
    void apply(String id,JsonNode snapshot);
    void problem(String id,String code);
}
