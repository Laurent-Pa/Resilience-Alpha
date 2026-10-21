# Keycloak + authenticator « reconnaissance faciale » (keycloak/face-authenticator).
# Contexte de build = keycloak/ :
#   docker build -t resilience-keycloak keycloak
# Maven tourne dans le conteneur de build : ni Java ni Maven à installer sur l'hôte.
FROM maven:3.9-eclipse-temurin-21 AS build
WORKDIR /src
COPY face-authenticator/pom.xml .
RUN mvn -q -B dependency:go-offline
COPY face-authenticator/src src
RUN mvn -q -B package

# Garder la version alignée sur keycloak.version du pom.xml.
FROM quay.io/keycloak/keycloak:26.8.0
# Pris en compte au démarrage (start-dev, ou `start` sans --optimized qui reconstruit).
COPY --from=build /src/target/face-authenticator.jar /opt/keycloak/providers/
