import Foundation
import AuthenticationServices
import CryptoKit
import AppKit

struct HeptabaseOAuthConnectResult {
    let accessToken: String
    let refreshToken: String?
    let expiresAt: Date?
    let scope: String?
}

final class HeptabaseOAuthManager {
    static let callbackScheme = "studentcrmnative"
    static let callbackURL = "studentcrmnative://oauth/heptabase/callback"
    static let requestedScope = "openid profile email offline_access space:read"
    static let resource = "https://api.heptabase.com/mcp"

    private let endpoint: URL
    private let session = URLSession.shared

    init(endpoint: URL) {
        self.endpoint = endpoint
    }

    func connect() async throws -> HeptabaseOAuthConnectResult {
        let resourceMetadata = try await fetchResourceMetadata()
        let issuerURL = try issuerURL(from: resourceMetadata)
        let configuration = try await fetchOpenIDConfiguration(from: issuerURL)
        let registration = try await registerClient(at: configuration.registrationEndpoint)

        let state = randomURLSafeString(length: 32)
        let codeVerifier = randomURLSafeString(length: 64)
        let codeChallenge = codeChallenge(for: codeVerifier)

        let authorizationURL = try buildAuthorizationURL(
            configuration: configuration,
            clientID: registration.clientID,
            state: state,
            codeChallenge: codeChallenge
        )

        let callbackURL = try await Self.authenticate(with: authorizationURL)
        let response = try parseAuthorizationResponse(callbackURL: callbackURL, expectedState: state)
        let tokenResponse = try await exchangeCodeForToken(
            configuration: configuration,
            clientID: registration.clientID,
            code: response.code,
            codeVerifier: codeVerifier
        )

        return HeptabaseOAuthConnectResult(
            accessToken: tokenResponse.accessToken,
            refreshToken: tokenResponse.refreshToken,
            expiresAt: tokenResponse.expiresIn.map { Date().addingTimeInterval(TimeInterval($0)) },
            scope: tokenResponse.scope
        )
    }

    private func fetchResourceMetadata() async throws -> HeptabaseProtectedResourceMetadata {
        let resourceURL = endpoint
            .deletingLastPathComponent()
            .appendingPathComponent(".well-known/oauth-protected-resource")
        return try await fetchJSON(from: resourceURL, as: HeptabaseProtectedResourceMetadata.self)
    }

    private func issuerURL(from metadata: HeptabaseProtectedResourceMetadata) throws -> URL {
        guard let issuer = metadata.authorizationServers.first,
              let url = URL(string: issuer) else {
            throw HeptabaseOAuthError.invalidMetadata("找不到 authorization server")
        }
        return url
    }

    private func fetchOpenIDConfiguration(from issuerURL: URL) async throws -> HeptabaseOpenIDConfiguration {
        let configURL = issuerURL.appendingPathComponent(".well-known/openid-configuration")
        return try await fetchJSON(from: configURL, as: HeptabaseOpenIDConfiguration.self)
    }

    private func registerClient(at endpoint: URL?) async throws -> HeptabaseOAuthClientRegistration {
        guard let endpoint else {
            throw HeptabaseOAuthError.invalidMetadata("找不到 registration endpoint")
        }

        var request = URLRequest(url: endpoint)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.httpBody = try JSONEncoder().encode(
            HeptabaseOAuthClientRegistrationRequest(
                clientName: "StudentCRMNative",
                redirectUris: [Self.callbackURL],
                grantTypes: ["authorization_code", "refresh_token"],
                responseTypes: ["code"],
                applicationType: "native",
                tokenEndpointAuthMethod: "none"
            )
        )

        let response: HeptabaseOAuthClientRegistration = try await fetchJSON(request: request, as: HeptabaseOAuthClientRegistration.self)
        guard !response.clientID.isEmpty else {
            throw HeptabaseOAuthError.invalidMetadata("註冊 client 後沒有拿到 client_id")
        }
        return response
    }

    private func buildAuthorizationURL(
        configuration: HeptabaseOpenIDConfiguration,
        clientID: String,
        state: String,
        codeChallenge: String
    ) throws -> URL {
        guard var components = URLComponents(url: configuration.authorizationEndpoint, resolvingAgainstBaseURL: false) else {
            throw HeptabaseOAuthError.invalidMetadata("authorization endpoint 無效")
        }

        components.queryItems = [
            URLQueryItem(name: "response_type", value: "code"),
            URLQueryItem(name: "client_id", value: clientID),
            URLQueryItem(name: "redirect_uri", value: Self.callbackURL),
            URLQueryItem(name: "scope", value: Self.requestedScope),
            URLQueryItem(name: "state", value: state),
            URLQueryItem(name: "code_challenge", value: codeChallenge),
            URLQueryItem(name: "code_challenge_method", value: "S256"),
            URLQueryItem(name: "resource", value: Self.resource)
        ]

        guard let url = components.url else {
            throw HeptabaseOAuthError.invalidMetadata("無法組出授權 URL")
        }
        return url
    }

    @MainActor
    private static func authenticate(with url: URL) async throws -> URL {
        let coordinator = HeptabaseWebAuthCoordinator()
        return try await coordinator.authenticate(url: url, callbackScheme: Self.callbackScheme)
    }

    private func parseAuthorizationResponse(callbackURL: URL, expectedState: String) throws -> HeptabaseAuthorizationResponse {
        guard let components = URLComponents(url: callbackURL, resolvingAgainstBaseURL: false) else {
            throw HeptabaseOAuthError.invalidCallback("callback URL 格式錯誤")
        }

        let items = Dictionary(uniqueKeysWithValues: (components.queryItems ?? []).map { ($0.name, $0.value ?? "") })

        if let error = items["error"], !error.isEmpty {
            let description = items["error_description"] ?? error
            throw HeptabaseOAuthError.authorizationFailed(description)
        }

        guard let state = items["state"], state == expectedState else {
            throw HeptabaseOAuthError.invalidCallback("OAuth state 驗證失敗")
        }

        guard let code = items["code"], !code.isEmpty else {
            throw HeptabaseOAuthError.invalidCallback("Heptabase 沒有回傳 authorization code")
        }

        return HeptabaseAuthorizationResponse(code: code, state: state)
    }

    private func exchangeCodeForToken(
        configuration: HeptabaseOpenIDConfiguration,
        clientID: String,
        code: String,
        codeVerifier: String
    ) async throws -> HeptabaseOAuthTokenResponse {
        var request = URLRequest(url: configuration.tokenEndpoint)
        request.httpMethod = "POST"
        request.setValue("application/x-www-form-urlencoded", forHTTPHeaderField: "Content-Type")
        request.setValue("application/json", forHTTPHeaderField: "Accept")

        let bodyItems = [
            URLQueryItem(name: "grant_type", value: "authorization_code"),
            URLQueryItem(name: "client_id", value: clientID),
            URLQueryItem(name: "code", value: code),
            URLQueryItem(name: "redirect_uri", value: Self.callbackURL),
            URLQueryItem(name: "code_verifier", value: codeVerifier),
            URLQueryItem(name: "resource", value: Self.resource)
        ]

        var components = URLComponents()
        components.queryItems = bodyItems
        request.httpBody = components.percentEncodedQuery?.data(using: .utf8)

        return try await fetchJSON(request: request, as: HeptabaseOAuthTokenResponse.self)
    }

    private func fetchJSON<Response: Decodable>(from url: URL, as type: Response.Type) async throws -> Response {
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        return try await fetchJSON(request: request, as: type)
    }

    private func fetchJSON<Response: Decodable>(request: URLRequest, as type: Response.Type) async throws -> Response {
        let (data, response) = try await session.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse else {
            throw HeptabaseOAuthError.network("Heptabase OAuth 沒有回傳有效 HTTP 回應")
        }

        guard (200...299).contains(httpResponse.statusCode) else {
            let message = String(data: data, encoding: .utf8) ?? ""
            throw HeptabaseOAuthError.network("Heptabase OAuth HTTP \(httpResponse.statusCode)\n\(message)")
        }

        do {
            return try JSONDecoder().decode(type, from: data)
        } catch {
            let raw = String(data: data, encoding: .utf8) ?? ""
            throw HeptabaseOAuthError.network("Heptabase OAuth JSON 解析失敗\n\(raw)")
        }
    }

    private func randomURLSafeString(length: Int) -> String {
        let alphabet = Array("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-._~")
        return String((0..<length).compactMap { _ in alphabet.randomElement() })
    }

    private func codeChallenge(for verifier: String) -> String {
        let digest = SHA256.hash(data: Data(verifier.utf8))
        return Data(digest).base64EncodedString()
            .replacingOccurrences(of: "+", with: "-")
            .replacingOccurrences(of: "/", with: "_")
            .replacingOccurrences(of: "=", with: "")
    }
}

@MainActor
private final class HeptabaseWebAuthCoordinator: NSObject, ASWebAuthenticationPresentationContextProviding {
    private var session: ASWebAuthenticationSession?

    func authenticate(url: URL, callbackScheme: String) async throws -> URL {
        try await withCheckedThrowingContinuation { continuation in
            let session = ASWebAuthenticationSession(
                url: url,
                callbackURLScheme: callbackScheme
            ) { callbackURL, error in
                if let error {
                    continuation.resume(throwing: HeptabaseOAuthError.authorizationFailed(error.localizedDescription))
                    return
                }

                guard let callbackURL else {
                    continuation.resume(throwing: HeptabaseOAuthError.invalidCallback("Heptabase 沒有回傳 callback URL"))
                    return
                }

                continuation.resume(returning: callbackURL)
            }

            session.presentationContextProvider = self
            session.prefersEphemeralWebBrowserSession = false
            self.session = session

            guard session.start() else {
                continuation.resume(throwing: HeptabaseOAuthError.authorizationFailed("無法啟動 Heptabase OAuth 視窗"))
                return
            }
        }
    }

    func presentationAnchor(for session: ASWebAuthenticationSession) -> ASPresentationAnchor {
        NSApp.windows.first { $0.isKeyWindow } ?? NSApp.windows.first ?? ASPresentationAnchor()
    }
}

private struct HeptabaseProtectedResourceMetadata: Decodable {
    let authorizationServers: [String]

    private enum CodingKeys: String, CodingKey {
        case authorizationServers = "authorization_servers"
    }
}

private struct HeptabaseOpenIDConfiguration: Decodable {
    let authorizationEndpoint: URL
    let tokenEndpoint: URL
    let registrationEndpoint: URL?

    private enum CodingKeys: String, CodingKey {
        case authorizationEndpoint = "authorization_endpoint"
        case tokenEndpoint = "token_endpoint"
        case registrationEndpoint = "registration_endpoint"
    }
}

private struct HeptabaseOAuthClientRegistrationRequest: Encodable {
    let clientName: String
    let redirectUris: [String]
    let grantTypes: [String]
    let responseTypes: [String]
    let applicationType: String
    let tokenEndpointAuthMethod: String

    private enum CodingKeys: String, CodingKey {
        case clientName = "client_name"
        case redirectUris = "redirect_uris"
        case grantTypes = "grant_types"
        case responseTypes = "response_types"
        case applicationType = "application_type"
        case tokenEndpointAuthMethod = "token_endpoint_auth_method"
    }
}

private struct HeptabaseOAuthClientRegistration: Decodable {
    let clientID: String

    private enum CodingKeys: String, CodingKey {
        case clientID = "client_id"
    }
}

private struct HeptabaseAuthorizationResponse {
    let code: String
    let state: String
}

private struct HeptabaseOAuthTokenResponse: Decodable {
    let accessToken: String
    let refreshToken: String?
    let expiresIn: Int?
    let scope: String?

    private enum CodingKeys: String, CodingKey {
        case accessToken = "access_token"
        case refreshToken = "refresh_token"
        case expiresIn = "expires_in"
        case scope
    }
}

private enum HeptabaseOAuthError: LocalizedError {
    case invalidMetadata(String)
    case authorizationFailed(String)
    case invalidCallback(String)
    case network(String)

    var errorDescription: String? {
        switch self {
        case .invalidMetadata(let message),
             .authorizationFailed(let message),
             .invalidCallback(let message),
             .network(let message):
            return message
        }
    }
}
