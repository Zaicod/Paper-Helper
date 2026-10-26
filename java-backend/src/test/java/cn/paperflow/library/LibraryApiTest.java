package cn.paperflow.library;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.ResultActions;

import java.util.Map;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
class LibraryApiTest {
    @Autowired MockMvc mvc;
    @Autowired ObjectMapper json;
    @Autowired JdbcTemplate jdbc;

    @Test void collectionCrudIsOwnedAndNamesAreUniquePerOwner() throws Exception {
        var a = user(); var b = user();
        long id = create(a, "  My Research  ");
        create(b, "My Research");
        request(post("/api/library/collections"), a, Map.of("name", "my research"))
                .andExpect(status().isConflict());
        mvc.perform(get("/api/library/collections").session(a))
                .andExpect(status().isOk()).andExpect(jsonPath("$.data.total").value(1))
                .andExpect(jsonPath("$.data.collections[0].name").value("My Research"));
        mvc.perform(get("/api/library/collections").session(b).param("query", "Research"))
                .andExpect(jsonPath("$.data.total").value(1));
        mvc.perform(get("/api/library/collections/{id}", id).session(a))
                .andExpect(status().isOk()).andExpect(jsonPath("$.data.paper_count").value(0))
                .andExpect(jsonPath("$.data.papers").isEmpty()).andExpect(jsonPath("$.data.mind_maps").isEmpty());
        request(put("/api/library/collections/" + id), a, Map.of("name", "Changed", "description", "notes"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.data.description").value("notes"));
        request(put("/api/library/collections/" + id + "/note"), a, Map.of("content", "overview"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.data.content").value("overview"));
        mvc.perform(get("/api/library/collections/{id}", id).session(a))
                .andExpect(jsonPath("$.data.overall_note").value("overview"));
        mvc.perform(delete("/api/library/collections/{id}", id).session(a).with(csrf()))
                .andExpect(status().isNoContent());
        mvc.perform(get("/api/library/collections/{id}", id).session(a)).andExpect(status().isNotFound());
    }

    @Test void otherUserCannotReadOrMutateCollectionOrDiscoverItThroughQuery() throws Exception {
        var a = user(); var b = user(); long id = create(a, "PrivateUnique");
        request(put("/api/library/collections/" + id), a,
                Map.of("name", "PrivateUnique", "description", "secret description match")).andExpect(status().isOk());
        long paper = json.readTree(request(post("/api/library/collections/" + id + "/papers"), a, paper("ownership"))
                .andExpect(status().isCreated()).andReturn().getResponse().getContentAsString()).path("data").get("id").asLong();
        mvc.perform(get("/api/library/collections/{id}", id).session(b)).andExpect(status().isNotFound());
        request(put("/api/library/collections/" + id), b, Map.of("name", "Stolen")).andExpect(status().isNotFound());
        mvc.perform(delete("/api/library/collections/{id}", id).session(b).with(csrf())).andExpect(status().isNotFound());
        request(post("/api/library/collections/" + id + "/papers"), b, paper("evil")).andExpect(status().isNotFound());
        request(put("/api/library/collections/" + id + "/note"), b, Map.of("content", "evil")).andExpect(status().isNotFound());
        request(put("/api/library/collections/" + id + "/paper-note"), b,
                Map.of("source", "arxiv", "paper_id", "ownership", "content", "evil")).andExpect(status().isNotFound());
        mvc.perform(delete("/api/library/collections/{id}/papers/{paper}", id, paper).session(b).with(csrf()))
                .andExpect(status().isNotFound());
        mvc.perform(get("/api/library/collections").session(b).param("query", "PrivateUnique"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.data.total").value(0));
        mvc.perform(get("/api/library/collections").session(b).param("query", "secret description"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.data.total").value(0));
    }

    @Test void globalPaperMetadataIsSharedButNotesAndMembershipRemainPrivate() throws Exception {
        var a = user(); var b = user(); long ca = create(a, "A"); long cb = create(b, "B");
        String key = UUID.randomUUID().toString();
        JsonNode first = json.readTree(request(post("/api/library/collections/" + ca + "/papers"), a, paper(key))
                .andExpect(status().isCreated()).andExpect(jsonPath("$.data.paper_id").value(key))
                .andReturn().getResponse().getContentAsString()).path("data");
        request(put("/api/library/collections/" + ca + "/paper-note"), a,
                Map.of("source", "arxiv", "paper_id", key, "content", "my note")).andExpect(status().isOk());
        request(post("/api/library/collections/" + ca + "/papers"), a, paper(key))
                .andExpect(status().isCreated()).andExpect(jsonPath("$.data.note").value("my note"));
        var otherMetadata = new java.util.HashMap<>(paper(key)); otherMetadata.put("title", "Overwrite attempt");
        request(post("/api/library/collections/" + cb + "/papers"), b, otherMetadata)
                .andExpect(status().isCreated()).andExpect(jsonPath("$.data.id").value(first.get("id").asLong()))
                .andExpect(jsonPath("$.data.title").value("Evidence paper")).andExpect(jsonPath("$.data.note").value(""));
        mvc.perform(delete("/api/library/collections/{id}/papers/{paper}", ca, first.get("id").asLong())
                .session(a).with(csrf())).andExpect(status().isNoContent());
        request(put("/api/library/collections/" + ca + "/paper-note"), a,
                Map.of("source", "arxiv", "paper_id", key, "content", "missing")) .andExpect(status().isNotFound());
        mvc.perform(get("/api/library/collections/{id}", cb).session(b))
                .andExpect(jsonPath("$.data.paper_count").value(1)).andExpect(jsonPath("$.data.papers[0].title").value("Evidence paper"));
    }

    @Test void inputConstraintsRejectInvalidNamesNotesPaginationAndUrls() throws Exception {
        var a = user(); long id = create(a, "Valid");
        for (String name : new String[]{" ", "x".repeat(256)})
            request(post("/api/library/collections"), a, Map.of("name", name)).andExpect(status().isBadRequest());
        for (String size : new String[]{"0", "101"})
            mvc.perform(get("/api/library/collections").session(a).param("size", size)).andExpect(status().isBadRequest());
        mvc.perform(get("/api/library/collections").session(a).param("page", "-1")).andExpect(status().isBadRequest());
        request(put("/api/library/collections/" + id + "/note"), a, Map.of("content", "x".repeat(50001)))
                .andExpect(status().isBadRequest());
        var bad = new java.util.HashMap<>(paper("bad")); bad.put("page_url", "file:///private");
        request(post("/api/library/collections/" + id + "/papers"), a, bad).andExpect(status().isBadRequest());
        bad.put("page_url", "https://example.com"); bad.put("abstract", "中".repeat(10001));
        request(post("/api/library/collections/" + id + "/papers"), a, bad).andExpect(status().isBadRequest());
    }

    @Test void collectionPaginationAndSearchDoNotChangeOwnershipScope() throws Exception {
        var a = user(); var b = user();
        create(a, "Alpha"); create(a, "Beta"); create(a, "Gamma"); create(b, "Alpha");
        mvc.perform(get("/api/library/collections").session(a).param("page", "1").param("size", "2"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.data.total").value(3))
                .andExpect(jsonPath("$.data.page").value(1)).andExpect(jsonPath("$.data.size").value(2))
                .andExpect(jsonPath("$.data.collections.length()").value(1));
        mvc.perform(get("/api/library/collections").session(a).param("query", "ALPHA"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.data.total").value(1));
    }

    @Test void failedMembershipInsertRollsBackNewPaperAsOneTransaction() throws Exception {
        var a = user(); long id = create(a, "Rollback"); String key = UUID.randomUUID().toString();
        // Inject a real database failure after the new metadata has been inserted.
        jdbc.execute("ALTER TABLE pf_collection_papers ADD CONSTRAINT test_reject_new_link CHECK (collection_id <> " + id + ")");
        try {
            request(post("/api/library/collections/" + id + "/papers"), a, paper(key)).andExpect(status().isConflict());
            assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM pf_papers WHERE source = ? AND external_id = ?",
                    Long.class, "arxiv", key)).isZero();
            mvc.perform(get("/api/library/collections/{id}", id).session(a)).andExpect(jsonPath("$.data.paper_count").value(0));
        } finally {
            jdbc.execute("ALTER TABLE pf_collection_papers DROP CONSTRAINT test_reject_new_link");
        }
    }

    @Test void paperMetadataEditsArePrivateToOneMembershipAndSurviveRepeatedAttachment() throws Exception {
        var a = user(); var b = user();
        long first = create(a, "Edited collection");
        long second = create(a, "Other owned collection");
        long other = create(b, "Other user's collection");
        String key = UUID.randomUUID().toString();
        JsonNode attached = json.readTree(request(post("/api/library/collections/" + first + "/papers"), a, paper(key))
                .andExpect(status().isCreated()).andReturn().getResponse().getContentAsString()).path("data");
        long paperId = attached.path("id").asLong();
        request(post("/api/library/collections/" + second + "/papers"), a, paper(key)).andExpect(status().isCreated());
        request(post("/api/library/collections/" + other + "/papers"), b, paper(key)).andExpect(status().isCreated());
        request(put("/api/library/collections/" + first + "/paper-note"), a,
                Map.of("source", "arxiv", "paper_id", key, "content", "keep my note")).andExpect(status().isOk());
        String item = "/api/library/collections/" + first + "/papers/" + paperId;
        var edited = new java.util.HashMap<>(paper(key));
        edited.put("title", "My corrected title");
        edited.put("abstract", "My corrected evidence");
        edited.put("authors", java.util.List.of("陈研究员", "Alice"));
        edited.put("categories", java.util.List.of("cs.IR"));
        edited.put("published", "2026-10-19");
        edited.put("page_url", "https://example.test/corrected");
        edited.put("pdf_url", "https://example.test/corrected.pdf");
        request(put(item), a, edited).andExpect(status().isOk())
                .andExpect(jsonPath("$.data.title").value("My corrected title"))
                .andExpect(jsonPath("$.data.metadata_edited").value(true))
                .andExpect(jsonPath("$.data.note").value("keep my note"));
        mvc.perform(get(item).session(a)).andExpect(status().isOk())
                .andExpect(jsonPath("$.data.abstract").value("My corrected evidence"))
                .andExpect(jsonPath("$.data.authors[0]").value("陈研究员"))
                .andExpect(jsonPath("$.data.categories[0]").value("cs.IR"))
                .andExpect(jsonPath("$.data.published").value("2026-10-19"))
                .andExpect(jsonPath("$.data.page_url").value("https://example.test/corrected"));
        mvc.perform(get("/api/library/collections/{id}", first).session(a))
                .andExpect(jsonPath("$.data.papers[0].title").value("My corrected title"));
        mvc.perform(get("/api/library/collections/{id}/papers/{paper}", second, paperId).session(a))
                .andExpect(jsonPath("$.data.title").value("Evidence paper"))
                .andExpect(jsonPath("$.data.metadata_edited").value(false));
        mvc.perform(get("/api/library/collections/{id}/papers/{paper}", other, paperId).session(b))
                .andExpect(jsonPath("$.data.title").value("Evidence paper"));
        assertThat(jdbc.queryForObject("SELECT title FROM pf_papers WHERE id = ?", String.class, paperId))
                .isEqualTo("Evidence paper");
        request(post("/api/library/collections/" + first + "/papers"), a, paper(key)).andExpect(status().isCreated())
                .andExpect(jsonPath("$.data.title").value("My corrected title"))
                .andExpect(jsonPath("$.data.note").value("keep my note"))
                .andExpect(jsonPath("$.data.metadata_edited").value(true));
        mvc.perform(get(item).session(b)).andExpect(status().isNotFound());
        request(put(item), b, edited).andExpect(status().isNotFound());
    }

    @Test void invalidMetadataEditsCannotChangeIdentityOrPersistUnsafeUrls() throws Exception {
        var a = user(); long collection = create(a, "Validation"); String key = UUID.randomUUID().toString();
        long paperId = json.readTree(request(post("/api/library/collections/" + collection + "/papers"), a, paper(key))
                .andExpect(status().isCreated()).andReturn().getResponse().getContentAsString()).path("data").path("id").asLong();
        String item = "/api/library/collections/" + collection + "/papers/" + paperId;
        for (String field : java.util.List.of("source", "paper_id", "page_url", "pdf_url", "title")) {
            var invalid = new java.util.HashMap<>(paper(key));
            invalid.put(field, switch (field) {
                case "source" -> "manual";
                case "paper_id" -> "different-identity";
                case "page_url", "pdf_url" -> "file:///private";
                default -> "x".repeat(1025);
            });
            request(put(item), a, invalid).andExpect(status().isBadRequest());
        }
        var invalidAuthors = new java.util.HashMap<>(paper(key));
        invalidAuthors.put("authors", java.util.List.of("x".repeat(129)));
        request(put(item), a, invalidAuthors).andExpect(status().isBadRequest());
        mvc.perform(get(item).session(a)).andExpect(status().isOk())
                .andExpect(jsonPath("$.data.title").value("Evidence paper"))
                .andExpect(jsonPath("$.data.metadata_edited").value(false));
        assertThat(jdbc.queryForObject("SELECT metadata_json FROM pf_collection_papers WHERE collection_id = ? AND paper_id = ?",
                String.class, collection, paperId)).isNull();
    }

    @Test void individualPaperReadAndEditRequireOwnedExistingMembership() throws Exception {
        var a = user(); long collection = create(a, "Empty");
        long second = create(a, "Contains paper"); String key = UUID.randomUUID().toString();
        long paperId = json.readTree(request(post("/api/library/collections/" + second + "/papers"), a, paper(key))
                .andExpect(status().isCreated()).andReturn().getResponse().getContentAsString()).path("data").path("id").asLong();
        String missingItem = "/api/library/collections/" + collection + "/papers/" + paperId;
        mvc.perform(get(missingItem).session(a)).andExpect(status().isNotFound());
        request(put(missingItem), a, paper(key)).andExpect(status().isNotFound());
        mvc.perform(get(missingItem)).andExpect(status().isUnauthorized());
    }

    private Map<String, Object> paper(String key) {
        return Map.of("source", "arxiv", "paper_id", key, "title", "Evidence paper", "abstract", "Evidence",
                "authors", java.util.List.of("Alice"), "categories", java.util.List.of("cs.AI"),
                "page_url", "https://arxiv.org/abs/1234", "pdf_url", "https://arxiv.org/pdf/1234");
    }
    private long create(MockHttpSession session, String name) throws Exception {
        return json.readTree(request(post("/api/library/collections"), session, Map.of("name", name))
                .andExpect(status().isCreated()).andReturn().getResponse().getContentAsString()).path("data").get("id").asLong();
    }
    private MockHttpSession user() throws Exception {
        String name = "u" + UUID.randomUUID().toString().replace("-", "").substring(0, 20);
        var response = mvc.perform(post("/api/auth/register").with(csrf()).contentType("application/json")
                .content(json.writeValueAsString(Map.of("username", name, "email", name + "@example.com", "password", "ValidPassword123!"))))
                .andExpect(status().isCreated()).andReturn();
        var session = (MockHttpSession) response.getRequest().getSession(false);
        assertThat(session).isNotNull(); return session;
    }
    private ResultActions request(org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder request,
                                  MockHttpSession session, Object body) throws Exception {
        return mvc.perform(request.session(session).with(csrf()).contentType("application/json").content(json.writeValueAsString(body)));
    }
}
