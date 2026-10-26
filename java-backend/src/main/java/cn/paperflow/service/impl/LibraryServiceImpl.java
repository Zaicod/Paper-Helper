package cn.paperflow.service.impl;

import cn.paperflow.service.LibraryService;
import cn.paperflow.mapper.*;
import cn.paperflow.entity.*;
import cn.paperflow.dto.*;
import cn.paperflow.vo.*;
import java.time.Instant;

import cn.paperflow.common.ApiException;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.net.URI;
import java.net.URISyntaxException;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

@Service
public class LibraryServiceImpl implements LibraryService {
    private final CollectionMapper collections;
    private final PaperMapper papers;
    private final CollectionPaperMapper links;
    private final ObjectMapper json;

    public LibraryServiceImpl(CollectionMapper collections, PaperMapper papers,
                          CollectionPaperMapper links, ObjectMapper json) {
        this.collections = collections; this.papers = papers; this.links = links; this.json = json;
    }

    @Transactional(readOnly = true)
    public CollectionPageVO list(long owner, String query, int page, int size) {
        if (page < 0 || size < 1 || size > 100 || query.length() > 255)
            throw new ApiException(HttpStatus.BAD_REQUEST, "分页或检索参数无效");
        String search = query.strip();
        var result = collections.searchOwned(owner, search, (long) page * size, size);
        return new CollectionPageVO(result.stream().map(this::summary).toList(), collections.countOwned(owner, search), page, size);
    }

    @Transactional
    public CollectionVO create(long owner, CollectionDTO input) {
        String normalized = normalized(input.name());
        if (collections.countSameName(owner, normalized, 0) > 0)
            throw new ApiException(HttpStatus.CONFLICT, "你已有同名收藏夹");
        PaperCollection collection = new PaperCollection();
        collection.setOwnerId(owner);
        collection.setName(input.name());
        collection.setNameNormalized(normalized);
        collection.setDescription(input.description());
        collection.setOverallNote("");
        collection.setCreatedAt(Instant.now());
        collections.insert(collection);
        return summary(collection);
    }

    @Transactional
    public CollectionVO update(long owner, long id, CollectionDTO input) {
        PaperCollection collection = owned(owner, id);
        String normalized = normalized(input.name());
        if (collections.countSameName(owner, normalized, id) > 0)
            throw new ApiException(HttpStatus.CONFLICT, "你已有同名收藏夹");
        collection.setName(input.name());
        collection.setNameNormalized(normalized);
        collection.setDescription(input.description());
        collections.update(collection);
        return summary(collection);
    }

    @Transactional(readOnly = true)
    public CollectionDetailVO detail(long owner, long id) {
        PaperCollection collection = owned(owner, id);
        List<CollectionPaper> membership = links.findByCollectionId(id);
        Map<Long, Paper> records = membership.isEmpty() ? Map.of() :
            papers.findAllById(membership.stream().map(CollectionPaper::getPaperId).toList())
                .stream().collect(Collectors.toMap(Paper::getId, Function.identity()));
        List<PaperVO> views = membership.stream().map(link -> view(records.get(link.getPaperId()), link)).toList();
        return new CollectionDetailVO(id, collection.getName(), collection.getDescription(), views.size(),
            collection.getOverallNote(), views, List.of(), List.of());
    }

    @Transactional
    public void delete(long owner, long id) {
        owned(owner, id);
        links.deleteAllForCollection(id);
        collections.delete(owner, id);
    }

    @Transactional
    public String collectionNote(long owner, long id, String content) {
        owned(owner, id);
        collections.updateNote(owner, id, content);
        return content;
    }

    @Transactional
    public PaperVO addPaper(long owner, long id, PaperDTO input) {
        owned(owner, id);
        validateUrl(input.pageUrl());
        if (input.pdfUrl() != null) validateUrl(input.pdfUrl());
        // Existing shared metadata is immutable from this user-facing import route.
        Paper paper = papers.findBySourceAndExternalId(input.source(), input.paperId()).orElseGet(() -> {
            Paper created = new Paper();
            created.setSource(input.source());
            created.setExternalId(input.paperId());
            created.setTitle(input.title());
            created.setAbstractText(input.abstractText());
            created.setAuthorsJson(encode(input.authors()));
            created.setCategoriesJson(encode(input.categories()));
            created.setPublished(input.published());
            created.setPageUrl(input.pageUrl());
            created.setPdfUrl(input.pdfUrl());
            created.setCreatedAt(Instant.now());
            papers.insert(created);
            return created;
        });
        CollectionPaper link = links.findByCollectionIdAndPaperId(id, paper.getId()).orElseGet(() -> {
            CollectionPaper created = new CollectionPaper();
            created.setCollectionId(id);
            created.setPaperId(paper.getId());
            created.setNote("");
            created.setAddedAt(Instant.now());
            links.insert(created);
            return created;
        });
        return view(paper, link);
    }

    @Transactional
    public void removePaper(long owner, long id, long paperId) {
        owned(owner, id);
        CollectionPaper link = links.findByCollectionIdAndPaperId(id, paperId).orElseThrow(LibraryServiceImpl::missing);
        links.delete(link);
    }

    @Transactional(readOnly = true)
    public PaperVO paper(long owner, long id, long paperId) {
        owned(owner, id);
        CollectionPaper link = links.findByCollectionIdAndPaperId(id, paperId).orElseThrow(LibraryServiceImpl::missing);
        return view(sharedPaper(link), link);
    }

    @Transactional
    public PaperVO updatePaper(long owner, long id, long paperId, PaperDTO input) {
        owned(owner, id);
        CollectionPaper link = links.findByCollectionIdAndPaperId(id, paperId).orElseThrow(LibraryServiceImpl::missing);
        Paper paper = sharedPaper(link);
        if (!paper.getSource().equals(input.source()) || !paper.getExternalId().equals(input.paperId()))
            throw new ApiException(HttpStatus.BAD_REQUEST, "来源和论文 ID 不可修改；如需更换论文，请重新添加");
        validateUrl(input.pageUrl());
        if (input.pdfUrl() != null) validateUrl(input.pdfUrl());
        // The personal snapshot belongs to this membership. Never update shared metadata.
        link.setMetadataJson(encode(input));
        link.setMetadataEdited(true);
        links.updateMetadata(link);
        return view(paper, link);
    }

    @Transactional
    public String paperNote(long owner, long id, PaperNoteDTO input) {
        owned(owner, id);
        Paper paper = papers.findBySourceAndExternalId(input.source(), input.paperId()).orElseThrow(LibraryServiceImpl::missing);
        CollectionPaper link = links.findByCollectionIdAndPaperId(id, paper.getId()).orElseThrow(LibraryServiceImpl::missing);
        link.setNote(input.content());
        links.updateNote(link);
        return input.content();
    }

    private PaperCollection owned(long owner, long id) {
        return collections.findOwned(owner, id).orElseThrow(LibraryServiceImpl::missing);
    }
    private Paper sharedPaper(CollectionPaper link) {
        return papers.findAllById(List.of(link.getPaperId())).stream().findFirst().orElseThrow(LibraryServiceImpl::missing);
    }
    private static ApiException missing() { return new ApiException(HttpStatus.NOT_FOUND, "收藏夹或论文不存在"); }
    private static String normalized(String name) {
        String value = name.toLowerCase(Locale.ROOT);
        if (value.length() > 255) throw new ApiException(HttpStatus.BAD_REQUEST, "收藏夹名称过长");
        return value;
    }
    private CollectionVO summary(PaperCollection collection) {
        return new CollectionVO(collection.getId(), collection.getName(), collection.getDescription(), links.countByCollectionId(collection.getId()));
    }
    private PaperVO view(Paper paper, CollectionPaper link) {
        if (link.isMetadataEdited()) {
            PaperDTO metadata = decodeMetadata(link.getMetadataJson());
            return new PaperVO(paper.getId(), paper.getSource(), paper.getExternalId(), metadata.title(), metadata.abstractText(),
                metadata.authors(), metadata.categories(), metadata.published(), metadata.pageUrl(), metadata.pdfUrl(),
                link.getAddedAt(), link.getNote(), true);
        }
        return new PaperVO(paper.getId(), paper.getSource(), paper.getExternalId(), paper.getTitle(), paper.getAbstractText(),
            decode(paper.getAuthorsJson()), decode(paper.getCategoriesJson()), paper.getPublished(), paper.getPageUrl(),
            paper.getPdfUrl(), link.getAddedAt(), link.getNote(), false);
    }
    private String encode(Object values) {
        try { return json.writeValueAsString(values); }
        catch (JsonProcessingException exception) { throw new ApiException(HttpStatus.INTERNAL_SERVER_ERROR, "论文信息无法保存"); }
    }
    private PaperDTO decodeMetadata(String value) {
        if (value == null) throw new ApiException(HttpStatus.INTERNAL_SERVER_ERROR, "论文个人资料无法读取");
        try { return json.readValue(value, PaperDTO.class); }
        catch (JsonProcessingException exception) { throw new ApiException(HttpStatus.INTERNAL_SERVER_ERROR, "论文个人资料无法读取"); }
    }
    private List<String> decode(String value) {
        try { return json.readValue(value, new TypeReference<List<String>>() {}); }
        catch (JsonProcessingException exception) { throw new ApiException(HttpStatus.INTERNAL_SERVER_ERROR, "论文信息无法读取"); }
    }
    private static void validateUrl(String value) {
        try {
            URI url = new URI(value);
            if (!("https".equalsIgnoreCase(url.getScheme()) || "http".equalsIgnoreCase(url.getScheme()))
                    || url.getHost() == null || url.getUserInfo() != null)
                throw new ApiException(HttpStatus.BAD_REQUEST, "论文链接必须为有效的 HTTP(S) 地址");
        } catch (URISyntaxException exception) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "论文链接无效");
        }
    }
}
