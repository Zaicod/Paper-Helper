package cn.paperflow.service;

public interface UserRateLimitService {
    void search(long owner);
    void generation(long owner);
}
