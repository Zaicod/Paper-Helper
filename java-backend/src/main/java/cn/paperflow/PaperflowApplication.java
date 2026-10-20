package cn.paperflow;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.session.SessionAutoConfiguration;
import org.springframework.boot.autoconfigure.security.servlet.UserDetailsServiceAutoConfiguration;

@SpringBootApplication(exclude = {SessionAutoConfiguration.class, UserDetailsServiceAutoConfiguration.class})
public class PaperflowApplication {
    public static void main(String[] args) {
        SpringApplication.run(PaperflowApplication.class, args);
    }
}
