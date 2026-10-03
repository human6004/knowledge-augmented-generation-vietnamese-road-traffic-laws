package vn.luatgt.service;

import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.io.IOException;
import java.security.*;
import java.util.*;
import org.springframework.core.io.ClassPathResource;
import org.springframework.stereotype.Service;
import vn.luatgt.exception.ApiErrors;

@Service
public class KagSchema {
    private final JsonNode contract;
    private final String sha256, schemaSha256;
    private final ObjectMapper json;
    private static final Map<String,String> TYPES=Map.of("documents","LegalDocument","units","LegalUnit","signs","TrafficSign");
    private static final Map<String,String> IDS=Map.of("documents","doc_id","units","unit_id","signs","sign_id");
    public KagSchema(ObjectMapper json) throws IOException,NoSuchAlgorithmException {
        this.json=json;
        try(var input=new ClassPathResource("kag-schema/schema_contract.json").getInputStream()) {
            byte[] bytes=input.readAllBytes(); contract=json.readTree(bytes);
            sha256=HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
        }
        for(String key:List.of("namespace","node_properties","relations","identity_strategy","runtime_contract"))
            if(!contract.hasNonNull(key)) throw new IllegalStateException("KAG contract thiếu "+key);
        try(var input=new ClassPathResource("kag-schema/VietRoadTraffic.schema").getInputStream()) {
            schemaSha256=HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(input.readAllBytes()));
        }
        if(!schemaSha256.equals(contract.path("runtime_contract").path("schema_sha256").asText()))
            throw new IllegalStateException("KAG schema không khớp SHA-256 trong runtime contract");
    }
    public JsonNode contract() { return contract.deepCopy(); }
    public Map<String,String> identity() {
        return Map.of("namespace",contract.path("namespace").asText(),"schema_sha256",schemaSha256,"contract_sha256",sha256);
    }
    public ObjectNode normalize(String kind,ObjectNode input) {
        var n=input.deepCopy(); String type=TYPES.get(kind);
        if(type==null) return n;
        for(var property:contract.path("node_properties").path(type)) {
            String logical=property.path("logical_name").asText(), physical=property.path("schema_name").asText();
            if(!logical.equals(physical)&&n.has(physical)) {
                same(n,logical,physical); n.set(logical,n.get(physical)); n.remove(physical);
                if(property.path("contract_type").asText().equals("JSON_TEXT")&&n.path(logical).isTextual()) {
                    try { var decoded=json.readTree(n.path(logical).asText()); if(decoded==null||decoded.isMissingNode()) throw ApiErrors.bad(logical+": JSON_TEXT trống"); n.set(logical,decoded); }
                    catch(IOException e) { throw ApiErrors.bad(logical+": JSON_TEXT không hợp lệ"); }
                }
            }
        }
        String id=IDS.get(kind);
        if(n.has("id")) {
            same(n,id,"id");
            n.set(id,n.get("id")); n.remove("id");
            // Graph name is a technical identity; the WebApp sign label comes from ten.
            if(kind.equals("signs")&&n.path("name").equals(n.get(id))) n.remove("name");
        }
        same(n,"externalId",id);
        if(n.has(id)) n.set("externalId",n.get(id));
        else if(n.has("externalId")) n.set(id,n.get("externalId"));
        if(n.hasNonNull("externalId")) exactId(n,"externalId",kind.equals("units")?500:250);
        for(var property:contract.path("node_properties").path(type)) {
            String field=property.path("logical_name").asText();
            if(property.path("intrinsic").asBoolean()||!n.hasNonNull(field)) continue;
            var value=n.get(field);
            boolean valid=switch(property.path("contract_type").asText()) {
                case "TEXT","OPTIONAL_TEXT" -> value.isTextual();
                case "INTEGER","OPTIONAL_INTEGER" -> value.isIntegralNumber()&&value.canConvertToLong();
                case "BOOLEAN_ENCODING" -> value.isBoolean()||value.isTextual()&&Set.of("true","false").contains(value.asText());
                case "JSON_TEXT" -> true;
                default -> false;
            };
            if(!valid) throw ApiErrors.bad(field+": sai kiểu trong KAG contract");
        }
        if(kind.equals("units")&&n.hasNonNull("unit_type")) {
            boolean found=false; for(var value:contract.path("unit_type_values")) if(value.equals(n.get("unit_type"))) found=true;
            if(!found) throw ApiErrors.bad("unit_type không thuộc KAG contract");
        }
        if(kind.equals("units")&&n.hasNonNull("penalty_id")) same(n,"penalty_id","unit_id");
        if(kind.equals("documents")) {
            aliasDate(n,"ngay_hieu_luc","effective_from"); aliasDate(n,"ngay_het_hieu_luc","effective_to");
            if(!n.has("source")&&n.has("source_url")) n.set("source",n.get("source_url"));
        }
        return n;
    }
    private static void same(ObjectNode n,String a,String b) {
        if(n.has(a)&&n.has(b)&&!n.get(a).equals(n.get(b))) throw ApiErrors.bad(a+" và "+b+" không khớp; không tự sửa ID/dữ liệu nguồn");
    }
    private static void aliasDate(ObjectNode n,String web,String source) {
        if(n.hasNonNull(web)&&n.hasNonNull(source)&&!n.get(web).equals(n.get(source))) throw ApiErrors.bad(web+" và "+source+" không khớp");
        if(!n.hasNonNull(web)&&n.hasNonNull(source)) n.set(web,n.get(source));
    }
    public static String exactId(ObjectNode n,String field,int max) {
        var value=n.get(field);
        if(value==null||!value.isTextual()||value.asText().isBlank()||value.asText().length()>max) throw ApiErrors.bad(field+": cần ID nguồn nguyên trạng, tối đa "+max+" ký tự");
        return value.asText();
    }
}
