-- 로컬 개발용 DB와 전용 사용자를 만든다. root 계정으로 한 번만 실행한다.
-- 실행 전에 '여기에_비밀번호' 부분을 바꾸고, 같은 값을 .env의 DB_PASSWORD에 넣는다.
-- (이 파일에 실제 비밀번호를 적은 채로 커밋하지 말 것)

CREATE DATABASE IF NOT EXISTS reservation
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;

CREATE USER IF NOT EXISTS 'reservation_app'@'localhost' IDENTIFIED BY '여기에_비밀번호';

-- 앱 계정에는 이 DB에 대한 권한만 준다. (root를 앱에서 쓰지 않는다)
GRANT ALL PRIVILEGES ON reservation.* TO 'reservation_app'@'localhost';
FLUSH PRIVILEGES;
