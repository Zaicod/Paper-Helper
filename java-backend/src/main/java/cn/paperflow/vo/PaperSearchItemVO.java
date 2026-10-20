package cn.paperflow.vo;

import cn.paperflow.dto.PaperDTO;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;

/** Search metrics belong to provider results; they do not overwrite personal library metadata. */
public record PaperSearchItemVO(String source,String paperId,String title,@JsonProperty("abstract") String abstractText,
    List<String> authors,List<String> categories,String published,String pageUrl,String pdfUrl,Long citedByCount) {
    public static PaperSearchItemVO from(PaperDTO p,Long count){
        return new PaperSearchItemVO(p.source(),p.paperId(),p.title(),p.abstractText(),p.authors(),p.categories(),p.published(),p.pageUrl(),p.pdfUrl(),count);
    }
}
