package cn.paperflow.research;

import cn.paperflow.client.WorkerClient;
import cn.paperflow.common.ApiException;
import cn.paperflow.dto.ResearchTaskDTO;
import cn.paperflow.entity.ResearchTask;
import cn.paperflow.mapper.ResearchTaskMapper;
import cn.paperflow.service.LibraryService;
import cn.paperflow.service.impl.ResearchTaskServiceImpl;
import cn.paperflow.vo.CollectionDetailVO;
import cn.paperflow.vo.PaperVO;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import java.time.Instant;
import java.util.*;
import java.util.stream.IntStream;
import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;

class ResearchTaskPayloadTest {
    @Test void rejectsOversizedUtf8SnapshotBeforePersistingTask() {
        var mapper=mock(ResearchTaskMapper.class);var library=mock(LibraryService.class);var worker=mock(WorkerClient.class);
        when(worker.configured()).thenReturn(true);
        var papers=IntStream.rangeClosed(1,20).mapToObj(i->paper(i,"中".repeat(50000),"Evidence")).toList();
        when(library.detail(7,1)).thenReturn(new CollectionDetailVO(1,"Large notes","",20,"",papers,List.of(),List.of()));
        var documents=mock(cn.paperflow.service.PaperDocumentService.class);
        when(documents.requireReady(eq(7L),eq(1L),anyList())).thenAnswer(invocation->{
            Map<String,String> ready=new LinkedHashMap<>();for(PaperVO paper:invocation.<List<PaperVO>>getArgument(2)) ready.put(paper.paperId(),UUID.randomUUID().toString());return ready;
        });
        var service=new ResearchTaskServiceImpl(mapper,library,new ObjectMapper(),worker,1800,null,null,documents);
        var body=new ResearchTaskDTO(UUID.randomUUID().toString(),"Study","live",20,"abstract","qwen",null,1L,
            papers.stream().map(PaperVO::id).toList(),"study_report","","");
        assertThatThrownBy(()->service.submit(7,body)).isInstanceOfSatisfying(ApiException.class,error->{
            assertThat(error.status()).isEqualTo(HttpStatus.BAD_REQUEST);
            assertThat(error.getMessage()).contains("2 MiB").contains("笔记");
        });
        verify(mapper,never()).insert(any());
    }
    @Test void boundsResearchSnapshotsTooAndKeepsNormalStudyNotesIntact() {
        var mapper=mock(ResearchTaskMapper.class);var library=mock(LibraryService.class);var worker=mock(WorkerClient.class);
        when(worker.configured()).thenReturn(true);
        when(library.detail(7,1)).thenReturn(new CollectionDetailVO(1,"Large paper","",1,"",
            List.of(paper(1,"","中".repeat(800000))),List.of(),List.of()));
        var documents=mock(cn.paperflow.service.PaperDocumentService.class);
        when(documents.requireReady(eq(7L),eq(1L),anyList())).thenAnswer(invocation->{
            Map<String,String> ready=new LinkedHashMap<>();for(PaperVO paper:invocation.<List<PaperVO>>getArgument(2)) ready.put(paper.paperId(),UUID.randomUUID().toString());return ready;
        });
        var service=new ResearchTaskServiceImpl(mapper,library,new ObjectMapper(),worker,1800,null,null,documents);
        var research=new ResearchTaskDTO(UUID.randomUUID().toString(),"Research","live",1,"abstract","qwen",null,1L,List.of(1L));
        assertThatThrownBy(()->service.submit(7,research)).isInstanceOf(ApiException.class);
        verify(mapper,never()).insert(any());
        String note="中".repeat(50000);
        when(library.detail(7,1)).thenReturn(new CollectionDetailVO(1,"Normal","",1,note,List.of(paper(1,note,"Evidence")),List.of(),List.of()));
        var study=new ResearchTaskDTO(UUID.randomUUID().toString(),"Study","live",1,"abstract","qwen",null,1L,List.of(1L),"study_report","","");
        service.submit(7,study);
        var captor=org.mockito.ArgumentCaptor.forClass(ResearchTask.class);verify(mapper).insert(captor.capture());
        assertThat(captor.getValue().getPayloadJson()).contains(note);
    }
    private static PaperVO paper(int id,String note,String abstractText) {
        return new PaperVO(id,"manual","p"+id,"Paper "+id,abstractText,List.of(),List.of(),null,
            "https://example.test/"+id,"https://example.test/"+id+".pdf",Instant.now(),note,false);
    }
}
