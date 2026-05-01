---
trigger: always_on
---


## FastAPI

working directory 는 `backend` 이다.

```
backend/
    main.py
    core/
    app/
          domain/
          use_cases/
          adapters/
          infrastructure/
```

1. main.py 에 모든 것을 구현하지 마라.
2. 외부에서 넘어오은 DTO (DataTransferObject) 는 `adapters/schemas/` 에 구현하라.
3. API 앤드포인트는 `adapters/apis/` 에 구현하라.
4. DomainRepository 는 무엇을 할 것인가를 구현하는 것이며, `domain/` 에 구현하라.
  - 순수한 Python 코드여야 한다.
  - Entity 는 핵심 로직을 담는 객체이다. 단순한 데이터 덩어리가 아니라, user.activate()처럼 비지니스 규칙을 메서드로 가진다. DB 테이블 구조와 달라도 상관없다. 파일명과 클래스명 suffix 는 entity 로 한다.
  - Repository Interface 는 이름표만 붗여둔 추상 클래스이다. abc.ABC 를 사용하며, 내부 로직은 비어있다. 파일명과 클래스명 suffix 는 repository_abc 로 한다.
5. AdapterRepository 는 어떻게 저장할 것인가를 구현하는 것이며, `adapter/database/` 에 구현하라.
  - SQLAlchemy 등의 ORM 구현체이다.
  - DB 테이블과 1:1로 매핑되는 클래스이며 파일명과 클래스명 suffix 는 model 로 한다.
  - 실제 리포지토리 구현체이며, session.add() 나 session.commit() 쿼리 수행을 한다. 파일명과 클래스명 suffix 는 repository 로 한다.

## LangGraph Workflows

## Python 공통