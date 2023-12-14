.PHONY: build run stop rm rebuild

build:
	docker-compose build

run:
	docker-compose up -d

stop:
	docker-compose down

rm:
	docker rmi icons8

rebuild: stop rm build run
