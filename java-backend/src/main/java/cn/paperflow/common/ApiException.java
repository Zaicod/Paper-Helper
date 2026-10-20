package cn.paperflow.common;

import org.springframework.http.HttpStatus;

/** An intentional, user-safe API error. Never wrap raw database error text. */
public class ApiException extends RuntimeException {
    private final HttpStatus status;

    public ApiException(HttpStatus status, String detail) {
        super(detail);
        this.status = status;
    }

    public HttpStatus status() { return status; }
}
