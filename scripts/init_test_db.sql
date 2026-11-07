-- 테스트 전용 DB를 만든다. root 계정으로 한 번만 실행한다. (init_db.sql을 먼저 실행해 계정이 있어야 함)
-- 테스트는 이 DB의 테이블을 매번 만들고 데이터를 지우므로, 개발용 DB(reservation)와 반드시 분리한다.

CREATE DATABASE IF NOT EXISTS reservation_test
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;

GRANT ALL PRIVILEGES ON reservation_test.* TO 'reservation_app'@'localhost';
FLUSH PRIVILEGES;
