import Foundation

enum SidebarSection: String, CaseIterable, Identifiable {
    case dashboard
    case appleCEO

    var id: String { rawValue }

    var title: String {
        switch self {
        case .dashboard: return "學員總覽"
        case .appleCEO: return "蘋果總裁班"
        }
    }
}

struct StudentRecord: Identifiable, Hashable {
    let id: String
    let name: String
    let aliases: [String]
    let file: String
    let lessonsCount: Int
    let latestDate: String
    let nextLesson: String
    let tags: [String]
}

struct LessonRecord: Identifiable, Hashable {
    let id: String
    let date: String
    let title: String
    let preview: String
    let path: String
    let content: String
}

struct StudentPrediction: Hashable {
    let badge: String
    let status: String
    let style: Style
    let reason: String

    enum Style: Hashable {
        case full
        case short
        case placeholder
        case missing
    }
}

struct ProgramInfo: Hashable {
    let id: String
    let name: String
    let url: String
    let description: String
    let schedule: String
    let capacity: String
    let roundSize: Int
    let pricePerStudent: Int
    let validityRule: String
    let leaveRule: String
    let joinRule: String
}

struct VenueInfo: Hashable {
    let name: String
    let address: String
    let parking: String
    let metro: String
    let costPerPerson: Int
}

struct AttendeeDetail: Identifiable, Hashable, Codable {
    var id: String { name }
    let name: String
    let cumulative: String
}

struct AttendanceRecord: Identifiable, Hashable {
    let id: String
    let date: String
    let venue: String
    let attendeeCount: Int
    let attendeeDetails: [AttendeeDetail]
    let note: String

    var attendees: [String] { attendeeDetails.map(\.name) }
}


struct VenueLedgerRecord: Identifiable, Hashable {
    let id: String
    let date: String
    let type: String
    let amount: Int
    let headcount: Int?
    let note: String
    let balanceAfter: Int
}

struct StudentRoundRecord: Identifiable, Hashable {
    let id: String
    let studentName: String
    let label: String
    let paymentStatus: String
    let sessions: [String]
    let attendedCount: Int
    let expiryDate: String?
    let isExpired: Bool
    let isActive: Bool
    let sortOrder: Int

    var remainingCount: Int { max(0, 8 - attendedCount) }
    var isFollowup: Bool { attendedCount == 6 || attendedCount == 7 }
}

struct StudentRoundGroup: Identifiable, Hashable {
    let id: String
    let studentName: String
    let latestRound: StudentRoundRecord?
    let historyRounds: [StudentRoundRecord]
}

struct AliasMapping: Identifiable, Hashable {
    let id: String
    let alias: String
    let canonicalName: String
}

struct AppleCEOSummary: Hashable {
    let activeParticipantCount: Int
    let latestSessionDate: String
    let latestBalance: Int
    let latestBalanceLabel: String
    let totalSessions: Int
    let averageHeadcount: Double
    let activeStudents: [String]
    let followupStudents: [String]
    let completedStudents: [String]
    let expiredStudents: [String]

    static let empty = AppleCEOSummary(
        activeParticipantCount: 0,
        latestSessionDate: "尚無資料",
        latestBalance: 0,
        latestBalanceLabel: "$0",
        totalSessions: 0,
        averageHeadcount: 0,
        activeStudents: [],
        followupStudents: [],
        completedStudents: [],
        expiredStudents: []
    )
}

struct AttendancePreviewResult: Hashable {
    let status: String
    let requiresHumanConfirmation: Bool
    let willWrite: Bool
    let proposedRecord: AttendancePreviewRecord
    let affectedRounds: [AttendancePreviewRound]
    let warnings: [String]
    let summary: AttendancePreviewSummary
}

struct AttendancePreviewRecord: Hashable {
    let date: String
    let venue: String
    let attendeeCount: Int
    let attendees: [String]
    let note: String
}

struct AttendancePreviewRound: Identifiable, Hashable {
    var id: String { "\(studentName)-\(action)-\(after.attendedCount)" }
    let studentName: String
    let action: String
    let before: AttendancePreviewRoundState
    let after: AttendancePreviewRoundState
}

struct AttendancePreviewRoundState: Hashable {
    let label: String
    let sessions: [String]
    let attendedCount: Int
    let remainingCount: Int
}

struct AttendancePreviewSummary: Hashable {
    let attendeeCount: Int
    let matchedCount: Int
    let warningCount: Int
}

struct OneOnOneSummary: Hashable {
    let totalStudents: Int
    let pendingLessonsCount: Int
    let noNextLessonCount: Int
    let stableCount: Int
    let riskCount: Int
    let freezingCount: Int
    let pendingLessonNames: [String]
    let noNextLessonNames: [String]

    static let empty = OneOnOneSummary(
        totalStudents: 0,
        pendingLessonsCount: 0,
        noNextLessonCount: 0,
        stableCount: 0,
        riskCount: 0,
        freezingCount: 0,
        pendingLessonNames: [],
        noNextLessonNames: []
    )
}
