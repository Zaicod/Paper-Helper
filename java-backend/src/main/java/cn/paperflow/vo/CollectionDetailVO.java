package cn.paperflow.vo;

import java.util.List;

public record CollectionDetailVO(long id, String name, String description, long paperCount,
                                String overallNote, List<PaperVO> papers,
                                List<Object> mindMaps, List<String> researchRunIds) {}
