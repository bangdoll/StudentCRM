import Foundation
import SQLite3

enum DatabaseError: Error, LocalizedError {
    case openFailed
    case prepareFailed(String)
    case stepFailed(String)

    var errorDescription: String? {
        switch self {
        case .openFailed:
            return "無法開啟 SQLite 資料庫"
        case .prepareFailed(let sql):
            return "SQL 準備失敗：\(sql)"
        case .stepFailed(let sql):
            return "SQL 執行失敗：\(sql)"
        }
    }
}

final class DatabaseManager {
    private var db: OpaquePointer?

    deinit {
        sqlite3_close(db)
    }

    func prepare() throws {
        let fm = FileManager.default
        let appSupport = try fm.url(
            for: .applicationSupportDirectory,
            in: .userDomainMask,
            appropriateFor: nil,
            create: true
        )
        let folder = appSupport.appendingPathComponent("StudentCRMNative", isDirectory: true)
        try fm.createDirectory(at: folder, withIntermediateDirectories: true)
        let dbURL = folder.appendingPathComponent("studentcrm.sqlite3")

        if sqlite3_open(dbURL.path, &db) != SQLITE_OK {
            throw DatabaseError.openFailed
        }

        try execute("""
        CREATE TABLE IF NOT EXISTS students (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            aliases_json TEXT NOT NULL,
            file_path TEXT NOT NULL,
            lessons_count INTEGER NOT NULL,
            latest_date TEXT NOT NULL DEFAULT '',
            next_lesson TEXT NOT NULL,
            tags_json TEXT NOT NULL
        );
        """)

        // 遷移：如果舊表缺少 latest_date 欄位，自動補上
        try? execute("ALTER TABLE students ADD COLUMN latest_date TEXT NOT NULL DEFAULT '';")

        try execute("""
        CREATE TABLE IF NOT EXISTS app_meta (
            scope TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            PRIMARY KEY (scope, key)
        );
        """)

        try execute("""
        CREATE TABLE IF NOT EXISTS apple_attendance (
            id TEXT PRIMARY KEY,
            date TEXT NOT NULL,
            venue TEXT NOT NULL,
            attendee_count INTEGER NOT NULL,
            attendees_json TEXT NOT NULL,
            note TEXT NOT NULL
        );
        """)

        try execute("""
        CREATE TABLE IF NOT EXISTS apple_venue_ledger (
            id TEXT PRIMARY KEY,
            date TEXT NOT NULL,
            type TEXT NOT NULL,
            amount INTEGER NOT NULL,
            headcount INTEGER,
            note TEXT NOT NULL,
            balance_after INTEGER NOT NULL
        );
        """)

        try execute("""
        CREATE TABLE IF NOT EXISTS apple_rounds (
            id TEXT PRIMARY KEY,
            student_name TEXT NOT NULL,
            label TEXT NOT NULL,
            payment_status TEXT NOT NULL,
            sessions_json TEXT NOT NULL,
            attended_count INTEGER NOT NULL,
            expiry_date TEXT,
            is_expired INTEGER NOT NULL,
            is_active INTEGER NOT NULL,
            sort_order INTEGER NOT NULL
        );
        """)
    }

    func resetImportedData() throws {
        try execute("DELETE FROM students;")
        try execute("DELETE FROM app_meta WHERE scope IN ('program', 'venue');")
        try execute("DELETE FROM apple_attendance;")
        try execute("DELETE FROM apple_venue_ledger;")
        try execute("DELETE FROM apple_rounds;")
    }

    func replaceStudents(_ students: [StudentRecord]) throws {
        try execute("DELETE FROM students;")
        for student in students {
            try insertStudent(student)
        }
    }

    func replaceAppleCEOProgram(
        program: ProgramInfo,
        venue: VenueInfo,
        attendanceRecords: [AttendanceRecord],
        venueLedger: [VenueLedgerRecord],
        roundGroups: [StudentRoundGroup]
    ) throws {
        try execute("DELETE FROM app_meta WHERE scope IN ('program', 'venue');")
        try execute("DELETE FROM apple_attendance;")
        try execute("DELETE FROM apple_venue_ledger;")
        try execute("DELETE FROM apple_rounds;")

        try insertMeta(scope: "program", key: "id", value: program.id)
        try insertMeta(scope: "program", key: "name", value: program.name)
        try insertMeta(scope: "program", key: "url", value: program.url)
        try insertMeta(scope: "program", key: "description", value: program.description)
        try insertMeta(scope: "program", key: "schedule", value: program.schedule)
        try insertMeta(scope: "program", key: "capacity", value: program.capacity)
        try insertMeta(scope: "program", key: "round_size", value: String(program.roundSize))
        try insertMeta(scope: "program", key: "price_per_student", value: String(program.pricePerStudent))
        try insertMeta(scope: "program", key: "validity_rule", value: program.validityRule)
        try insertMeta(scope: "program", key: "leave_rule", value: program.leaveRule)
        try insertMeta(scope: "program", key: "join_rule", value: program.joinRule)

        try insertMeta(scope: "venue", key: "name", value: venue.name)
        try insertMeta(scope: "venue", key: "address", value: venue.address)
        try insertMeta(scope: "venue", key: "parking", value: venue.parking)
        try insertMeta(scope: "venue", key: "metro", value: venue.metro)
        try insertMeta(scope: "venue", key: "cost_per_person", value: String(venue.costPerPerson))

        for record in attendanceRecords {
            try insertAttendance(record)
        }

        for record in venueLedger {
            try insertVenueLedger(record)
        }

        for group in roundGroups {
            let rounds = [group.latestRound].compactMap { $0 } + group.historyRounds
            for round in rounds {
                try insertRound(round, sortOrder: round.sortOrder)
            }
        }
    }

    func execute(_ sql: String) throws {
        guard sqlite3_exec(db, sql, nil, nil, nil) == SQLITE_OK else {
            throw DatabaseError.stepFailed(sql)
        }
    }

    func insertStudent(_ student: StudentRecord) throws {
        try prepareAndRun(
            """
            INSERT INTO students (id, name, aliases_json, file_path, lessons_count, latest_date, next_lesson, tags_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """
        ) { stmt in
            self.bind(student.id, to: 1, in: stmt)
            self.bind(student.name, to: 2, in: stmt)
            self.bindJSONString(student.aliases, to: 3, in: stmt)
            self.bind(student.file, to: 4, in: stmt)
            sqlite3_bind_int(stmt, 5, Int32(student.lessonsCount))
            self.bind(student.latestDate, to: 6, in: stmt)
            self.bind(student.nextLesson, to: 7, in: stmt)
            self.bindJSONString(student.tags, to: 8, in: stmt)
        }
    }

    func insertMeta(scope: String, key: String, value: String) throws {
        try prepareAndRun(
            """
            INSERT OR REPLACE INTO app_meta (scope, key, value)
            VALUES (?, ?, ?);
            """
        ) { stmt in
            self.bind(scope, to: 1, in: stmt)
            self.bind(key, to: 2, in: stmt)
            self.bind(value, to: 3, in: stmt)
        }
    }

    func insertAttendance(_ record: AttendanceRecord) throws {
        try prepareAndRun(
            """
            INSERT OR REPLACE INTO apple_attendance (id, date, venue, attendee_count, attendees_json, note)
            VALUES (?, ?, ?, ?, ?, ?);
            """
        ) { stmt in
            self.bind(record.id, to: 1, in: stmt)
            self.bind(record.date, to: 2, in: stmt)
            self.bind(record.venue, to: 3, in: stmt)
            sqlite3_bind_int(stmt, 4, Int32(record.attendeeCount))
            self.bindAttendeeDetails(record.attendeeDetails, to: 5, in: stmt)
            self.bind(record.note, to: 6, in: stmt)
        }
    }

    func deleteAttendance(id: String) throws {
        try prepareAndRun(
            """
            DELETE FROM apple_attendance
            WHERE id = ?;
            """
        ) { stmt in
            self.bind(id, to: 1, in: stmt)
        }
    }

    func insertVenueLedger(_ record: VenueLedgerRecord) throws {
        try prepareAndRun(
            """
            INSERT OR REPLACE INTO apple_venue_ledger (id, date, type, amount, headcount, note, balance_after)
            VALUES (?, ?, ?, ?, ?, ?, ?);
            """
        ) { stmt in
            self.bind(record.id, to: 1, in: stmt)
            self.bind(record.date, to: 2, in: stmt)
            self.bind(record.type, to: 3, in: stmt)
            sqlite3_bind_int(stmt, 4, Int32(record.amount))
            if let headcount = record.headcount {
                sqlite3_bind_int(stmt, 5, Int32(headcount))
            } else {
                sqlite3_bind_null(stmt, 5)
            }
            self.bind(record.note, to: 6, in: stmt)
            sqlite3_bind_int(stmt, 7, Int32(record.balanceAfter))
        }
    }

    func deleteVenueLedger(id: String) throws {
        try prepareAndRun(
            """
            DELETE FROM apple_venue_ledger
            WHERE id = ?;
            """
        ) { stmt in
            self.bind(id, to: 1, in: stmt)
        }
    }

    func insertRound(_ record: StudentRoundRecord, sortOrder: Int) throws {
        try prepareAndRun(
            """
            INSERT OR REPLACE INTO apple_rounds (id, student_name, label, payment_status, sessions_json, attended_count, expiry_date, is_expired, is_active, sort_order)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """
        ) { stmt in
            self.bind(record.id, to: 1, in: stmt)
            self.bind(record.studentName, to: 2, in: stmt)
            self.bind(record.label, to: 3, in: stmt)
            self.bind(record.paymentStatus, to: 4, in: stmt)
            self.bindJSONString(record.sessions, to: 5, in: stmt)
            sqlite3_bind_int(stmt, 6, Int32(record.attendedCount))
            if let expiryDate = record.expiryDate {
                self.bind(expiryDate, to: 7, in: stmt)
            } else {
                sqlite3_bind_null(stmt, 7)
            }
            sqlite3_bind_int(stmt, 8, record.isExpired ? 1 : 0)
            sqlite3_bind_int(stmt, 9, record.isActive ? 1 : 0)
            sqlite3_bind_int(stmt, 10, Int32(sortOrder))
        }
    }

    func updateRound(_ record: StudentRoundRecord) throws {
        try prepareAndRun(
            """
            UPDATE apple_rounds
            SET student_name = ?, label = ?, payment_status = ?, sessions_json = ?, attended_count = ?, expiry_date = ?, is_expired = ?, is_active = ?, sort_order = ?
            WHERE id = ?;
            """
        ) { stmt in
            self.bind(record.studentName, to: 1, in: stmt)
            self.bind(record.label, to: 2, in: stmt)
            self.bind(record.paymentStatus, to: 3, in: stmt)
            self.bindJSONString(record.sessions, to: 4, in: stmt)
            sqlite3_bind_int(stmt, 5, Int32(record.attendedCount))
            if let expiryDate = record.expiryDate {
                self.bind(expiryDate, to: 6, in: stmt)
            } else {
                sqlite3_bind_null(stmt, 6)
            }
            sqlite3_bind_int(stmt, 7, record.isExpired ? 1 : 0)
            sqlite3_bind_int(stmt, 8, record.isActive ? 1 : 0)
            sqlite3_bind_int(stmt, 9, Int32(record.sortOrder))
            self.bind(record.id, to: 10, in: stmt)
        }
    }

    func fetchStudents() throws -> [StudentRecord] {
        try query(
            """
            SELECT id, name, aliases_json, file_path, lessons_count, COALESCE(latest_date, ''), next_lesson, tags_json
            FROM students
            ORDER BY
                CASE
                    WHEN next_lesson = '' OR next_lesson = '待定' OR next_lesson = '未安排' THEN 3
                    WHEN substr(next_lesson, 1, 10) < date('now', 'localtime') THEN 2
                    ELSE 1
                END,
                next_lesson ASC,
                name ASC;
            """
        ) { stmt in
            StudentRecord(
                id: self.text(stmt, column: 0),
                name: self.text(stmt, column: 1),
                aliases: self.decodeStringArray(self.text(stmt, column: 2)),
                file: self.text(stmt, column: 3),
                lessonsCount: Int(sqlite3_column_int(stmt, 4)),
                latestDate: self.text(stmt, column: 5),
                nextLesson: self.text(stmt, column: 6),
                tags: self.decodeStringArray(self.text(stmt, column: 7))
            )
        }
    }

    func fetchProgram() throws -> ProgramInfo? {
        let values = try fetchMeta(scope: "program")
        guard let id = values["id"] else { return nil }
        return ProgramInfo(
            id: id,
            name: values["name"] ?? "",
            url: values["url"] ?? "",
            description: values["description"] ?? "",
            schedule: values["schedule"] ?? "",
            capacity: values["capacity"] ?? "",
            roundSize: Int(values["round_size"] ?? "") ?? 8,
            pricePerStudent: Int(values["price_per_student"] ?? "") ?? 0,
            validityRule: values["validity_rule"] ?? "",
            leaveRule: values["leave_rule"] ?? "",
            joinRule: values["join_rule"] ?? ""
        )
    }

    func fetchVenue() throws -> VenueInfo? {
        let values = try fetchMeta(scope: "venue")
        guard let name = values["name"] else { return nil }
        return VenueInfo(
            name: name,
            address: values["address"] ?? "",
            parking: values["parking"] ?? "",
            metro: values["metro"] ?? "",
            costPerPerson: Int(values["cost_per_person"] ?? "") ?? 0
        )
    }

    func fetchAttendance() throws -> [AttendanceRecord] {
        try query(
            """
            SELECT id, date, venue, attendee_count, attendees_json, note
            FROM apple_attendance
            ORDER BY date DESC;
            """
        ) { stmt in
            AttendanceRecord(
                id: self.text(stmt, column: 0),
                date: self.text(stmt, column: 1),
                venue: self.text(stmt, column: 2),
                attendeeCount: Int(sqlite3_column_int(stmt, 3)),
                attendeeDetails: self.decodeAttendeeDetails(self.text(stmt, column: 4)),
                note: self.text(stmt, column: 5)
            )
        }
    }

    func fetchVenueLedger() throws -> [VenueLedgerRecord] {
        try query(
            """
            SELECT id, date, type, amount, headcount, note, balance_after
            FROM apple_venue_ledger
            ORDER BY date DESC, id DESC;
            """
        ) { stmt in
            let headcount = sqlite3_column_type(stmt, 4) == SQLITE_NULL ? nil : Int(sqlite3_column_int(stmt, 4))
            return VenueLedgerRecord(
                id: self.text(stmt, column: 0),
                date: self.text(stmt, column: 1),
                type: self.text(stmt, column: 2),
                amount: Int(sqlite3_column_int(stmt, 3)),
                headcount: headcount,
                note: self.text(stmt, column: 5),
                balanceAfter: Int(sqlite3_column_int(stmt, 6))
            )
        }
    }

    func fetchRoundGroups() throws -> [StudentRoundGroup] {
        let rounds: [StudentRoundRecord] = try query(
            """
            SELECT id, student_name, label, payment_status, sessions_json, attended_count, expiry_date, is_expired, is_active, sort_order
            FROM apple_rounds
            ORDER BY student_name COLLATE NOCASE, sort_order ASC;
            """
        ) { stmt in
            StudentRoundRecord(
                id: self.text(stmt, column: 0),
                studentName: self.text(stmt, column: 1),
                label: self.text(stmt, column: 2),
                paymentStatus: self.text(stmt, column: 3),
                sessions: self.decodeStringArray(self.text(stmt, column: 4)),
                attendedCount: Int(sqlite3_column_int(stmt, 5)),
                expiryDate: sqlite3_column_type(stmt, 6) == SQLITE_NULL ? nil : self.text(stmt, column: 6),
                isExpired: sqlite3_column_int(stmt, 7) == 1,
                isActive: sqlite3_column_int(stmt, 8) == 1,
                sortOrder: Int(sqlite3_column_int(stmt, 9))
            )
        }

        let grouped = Dictionary(grouping: rounds, by: \.studentName)
        return grouped.keys.sorted().map { name in
            let items = grouped[name] ?? []
            return StudentRoundGroup(
                id: name,
                studentName: name,
                latestRound: items.first,
                historyRounds: Array(items.dropFirst())
            )
        }
    }

    func fetchSummary() throws -> AppleCEOSummary {
        let attendance = try fetchAttendance()
        let rounds = try fetchRoundGroups().flatMap { group in
            [group.latestRound].compactMap { $0 } + group.historyRounds
        }
        let latestBalance = try queryScalarInt("SELECT COALESCE((SELECT balance_after FROM apple_venue_ledger ORDER BY date DESC, id DESC LIMIT 1), 0);")
        let activeStudents = uniqueNames(from: rounds.filter(\.isActive))
        let followupStudents = uniqueNames(from: rounds.filter(\.isFollowup))
        let completedStudents = uniqueNames(from: rounds.filter { $0.attendedCount >= 8 })
        let expiredStudents = uniqueNames(from: rounds.filter(\.isExpired))

        let totalHeadcount = attendance.reduce(0) { $0 + $1.attendeeCount }
        let average = attendance.isEmpty ? 0 : Double(totalHeadcount) / Double(attendance.count)
        return AppleCEOSummary(
            activeParticipantCount: activeStudents.count,
            latestSessionDate: attendance.first?.date ?? "尚無資料",
            latestBalance: latestBalance,
            latestBalanceLabel: Self.currency(latestBalance),
            totalSessions: attendance.count,
            averageHeadcount: average,
            activeStudents: activeStudents,
            followupStudents: followupStudents,
            completedStudents: completedStudents,
            expiredStudents: expiredStudents
        )
    }

    func fetchMetaValues(scope: String) throws -> [String: String] {
        try fetchMeta(scope: scope)
    }

    func deleteMeta(scope: String, key: String) throws {
        try prepareAndRun(
            """
            DELETE FROM app_meta
            WHERE scope = ? AND key = ?;
            """
        ) { stmt in
            self.bind(scope, to: 1, in: stmt)
            self.bind(key, to: 2, in: stmt)
        }
    }

    private func fetchMeta(scope: String) throws -> [String: String] {
        let rows: [(String, String)] = try query(
            """
            SELECT key, value
            FROM app_meta
            WHERE scope = ?
            ORDER BY key;
            """,
            binder: { stmt in self.bind(scope, to: 1, in: stmt) }
        ) { stmt in
            (self.text(stmt, column: 0), self.text(stmt, column: 1))
        }
        return Dictionary(uniqueKeysWithValues: rows)
    }

    private func queryScalarInt(_ sql: String) throws -> Int {
        let values: [Int] = try query(sql) { stmt in
            Int(sqlite3_column_int(stmt, 0))
        }
        return values.first ?? 0
    }

    private func uniqueNames(from rounds: [StudentRoundRecord]) -> [String] {
        Array(Set(rounds.map(\.studentName))).sorted()
    }

    private func prepareAndRun(_ sql: String, binder: (OpaquePointer) throws -> Void) throws {
        var statement: OpaquePointer?
        guard sqlite3_prepare_v2(db, sql, -1, &statement, nil) == SQLITE_OK, let statement else {
            throw DatabaseError.prepareFailed(sql)
        }
        defer { sqlite3_finalize(statement) }
        try binder(statement)
        guard sqlite3_step(statement) == SQLITE_DONE else {
            throw DatabaseError.stepFailed(sql)
        }
    }

    private func query<T>(
        _ sql: String,
        binder: ((OpaquePointer) throws -> Void)? = nil,
        map: (OpaquePointer) throws -> T
    ) throws -> [T] {
        var statement: OpaquePointer?
        guard sqlite3_prepare_v2(db, sql, -1, &statement, nil) == SQLITE_OK, let statement else {
            throw DatabaseError.prepareFailed(sql)
        }
        defer { sqlite3_finalize(statement) }
        if let binder {
            try binder(statement)
        }

        var items: [T] = []
        while sqlite3_step(statement) == SQLITE_ROW {
            items.append(try map(statement))
        }
        return items
    }

    private func bind(_ value: String, to index: Int32, in statement: OpaquePointer) {
        sqlite3_bind_text(statement, index, value, -1, SQLITE_TRANSIENT)
    }

    private func bindJSONString(_ values: [String], to index: Int32, in statement: OpaquePointer) {
        let encoded = (try? String(data: JSONEncoder().encode(values), encoding: .utf8)) ?? "[]"
        bind(encoded, to: index, in: statement)
    }

    private func bindAttendeeDetails(_ values: [AttendeeDetail], to index: Int32, in statement: OpaquePointer) {
        let encoded = (try? String(data: JSONEncoder().encode(values), encoding: .utf8)) ?? "[]"
        bind(encoded, to: index, in: statement)
    }

    private func text(_ statement: OpaquePointer, column: Int32) -> String {
        guard let cString = sqlite3_column_text(statement, column) else { return "" }
        return String(cString: cString)
    }

    private func decodeStringArray(_ json: String) -> [String] {
        guard let data = json.data(using: .utf8),
              let values = try? JSONDecoder().decode([String].self, from: data) else {
            return []
        }
        return values
    }

    private func decodeAttendeeDetails(_ json: String) -> [AttendeeDetail] {
        guard let data = json.data(using: .utf8) else { return [] }
        let decoder = JSONDecoder()

        // Try decoding as new format
        if let details = try? decoder.decode([AttendeeDetail].self, from: data) {
            return details
        }

        // Fallback to legacy string array
        if let names = try? decoder.decode([String].self, from: data) {
            return names.map { AttendeeDetail(name: $0, cumulative: "") }
        }

        return []
    }

    private static func currency(_ value: Int) -> String {
        let formatter = NumberFormatter()
        formatter.numberStyle = .decimal
        let formatted = formatter.string(from: NSNumber(value: value)) ?? "\(value)"
        return "$\(formatted)"
    }
}

private let SQLITE_TRANSIENT = unsafeBitCast(-1, to: sqlite3_destructor_type.self)
