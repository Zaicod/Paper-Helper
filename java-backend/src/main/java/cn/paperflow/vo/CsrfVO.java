package cn.paperflow.vo;

public class CsrfVO {
    private final String token;
    private final String headerName;

    public CsrfVO(String token, String headerName) {
        this.token = token;
        this.headerName = headerName;
    }
    public String getToken() { return token; }
    public String getHeaderName() { return headerName; }
}
