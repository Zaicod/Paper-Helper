package cn.paperflow.common;

/** 黑马课程常见的统一返回结构：成功 code=1，失败 code=0，HTTP 状态仍表达具体错误。 */
public record Result<T>(int code, String msg, T data) {
    public static <T> Result<T> success(T data) { return new Result<>(1,null,data); }
    public static Result<Void> error(String message) { return new Result<>(0,message,null); }
}
