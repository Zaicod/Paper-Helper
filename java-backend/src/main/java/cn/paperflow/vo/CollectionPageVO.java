package cn.paperflow.vo;

import java.util.List;

public record CollectionPageVO(List<CollectionVO> collections, long total, int page, int size) {}
