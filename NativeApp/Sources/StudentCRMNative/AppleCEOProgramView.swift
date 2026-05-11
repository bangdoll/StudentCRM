import SwiftUI

struct AppleCEOProgramView: View {
    @EnvironmentObject private var store: AppStore
    @State private var showingAttendanceSheet = false
    @State private var showingLedgerSheet = false
    @State private var editingAttendance: AttendanceRecord?
    @State private var editingLedger: VenueLedgerRecord?
    @State private var deletingAttendance: AttendanceRecord?
    @State private var deletingLedger: VenueLedgerRecord?
    @State private var aliasToDelete: AliasMapping?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                header
                summaryCards
                if let venue = store.venue { venueCard(venue) }
                aliasSection
                venueLedgerSection
                attendanceSection
                roundsSection
            }
            .padding(24)
        }
        .navigationTitle("蘋果總裁班")
        .sheet(isPresented: $showingAttendanceSheet) {
            AddAttendanceSheet()
                .environmentObject(store)
        }
        .sheet(item: $editingAttendance) { record in
            AddAttendanceSheet(editingRecord: record)
                .environmentObject(store)
        }
        .sheet(isPresented: $showingLedgerSheet) {
            AddVenueLedgerSheet()
                .environmentObject(store)
        }
        .sheet(item: $editingLedger) { record in
            AddVenueLedgerSheet(editingRecord: record)
                .environmentObject(store)
        }
        .alert("刪除上課紀錄", isPresented: Binding(get: {
            deletingAttendance != nil
        }, set: { if !$0 { deletingAttendance = nil } })) {
            Button("取消", role: .cancel) {
                deletingAttendance = nil
            }
            Button("刪除", role: .destructive) {
                if let record = deletingAttendance {
                    Task { await store.deleteAttendance(record) }
                }
                deletingAttendance = nil
            }
        } message: {
            Text("刪除後會同步回寫正式資料檔。")
        }
        .alert("刪除場地費紀錄", isPresented: Binding(get: {
            deletingLedger != nil
        }, set: { if !$0 { deletingLedger = nil } })) {
            Button("取消", role: .cancel) {
                deletingLedger = nil
            }
            Button("刪除", role: .destructive) {
                if let record = deletingLedger {
                    Task { await store.deleteVenueLedger(record) }
                }
                deletingLedger = nil
            }
        } message: {
            Text("刪除後會同步回寫正式資料檔。")
        }
        .alert("刪除學員別名", isPresented: Binding(get: {
            aliasToDelete != nil
        }, set: { if !$0 { aliasToDelete = nil } })) {
            Button("取消", role: .cancel) {
                aliasToDelete = nil
            }
            Button("刪除", role: .destructive) {
                if let mapping = aliasToDelete {
                    Task { await store.deleteAlias(mapping) }
                }
                aliasToDelete = nil
            }
        } message: {
            Text("刪除後，這個稱呼就不會再自動對應到正式學員。")
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 10) {
                    Text(store.program?.name ?? "蘋果總裁班")
                        .font(.largeTitle.bold())
                    Text(store.program?.description ?? "小班制數位管理與 AI 應用課程")
                        .foregroundStyle(.secondary)

                    HStack {
                        Label(store.program?.schedule ?? "每週四 14:00-17:00", systemImage: "calendar")
                        Label("每輪 \(store.program?.roundSize ?? 8) 堂", systemImage: "square.stack.3d.up")
                        Label("每人 $\(store.program?.pricePerStudent ?? 0)", systemImage: "dollarsign.circle")
                    }
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                }

                Spacer()

                VStack(alignment: .trailing, spacing: 10) {
                    Button("新增上課紀錄") {
                        showingAttendanceSheet = true
                    }
                    .buttonStyle(.borderedProminent)

                    Button("新增場地費紀錄") {
                        showingLedgerSheet = true
                    }
                    .buttonStyle(.bordered)

                    Button("同步班務 API") {
                        Task { await store.reloadAppleCEOProgramFromAPI() }
                    }
                    .buttonStyle(.bordered)

                    if !store.latestActionMessage.isEmpty {
                        Text(store.latestActionMessage)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .multilineTextAlignment(.trailing)
                            .frame(maxWidth: 260, alignment: .trailing)
                    }
                }
            }
        }
    }

    private var summaryCards: some View {
        HStack(spacing: 16) {
            SummaryCard(title: "目前有在上課", value: "\(store.summary.activeStudents.count) 位", note: store.summary.activeStudents.joined(separator: "、"))
            SummaryCard(title: "接近完成", value: "\(store.summary.followupStudents.count) 位", note: store.summary.followupStudents.joined(separator: "、"))
            SummaryCard(title: "已滿 8 堂", value: "\(store.summary.completedStudents.count) 位", note: store.summary.completedStudents.joined(separator: "、"))
            SummaryCard(title: "場地餘額", value: store.summary.latestBalanceLabel, note: "最近一堂：\(store.summary.latestSessionDate)")
        }
    }

    private var aliasSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("學員別名管理")
                    .font(.title2.bold())
                Spacer()
                Text("新增上課紀錄時，會先用這裡的別名對應正式學員")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            AddAliasRow()
                .environmentObject(store)

            if store.aliasMappings.isEmpty {
                Text("目前尚未建立自訂別名。")
                    .foregroundStyle(.secondary)
            } else {
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 240), spacing: 12)], spacing: 12) {
                    ForEach(store.aliasMappings) { mapping in
                        HStack {
                            VStack(alignment: .leading, spacing: 4) {
                                Text(mapping.alias)
                                    .font(.headline)
                                Text("→ \(mapping.canonicalName)")
                                    .font(.subheadline)
                                    .foregroundStyle(.secondary)
                            }
                            Spacer()
                            Button("刪除") {
                                aliasToDelete = mapping
                            }
                            .buttonStyle(.borderless)
                            .foregroundStyle(.red)
                        }
                        .padding(14)
                        .background(Color(nsColor: .windowBackgroundColor))
                        .clipShape(RoundedRectangle(cornerRadius: 14))
                    }
                }
            }
        }
    }

    private func venueCard(_ venue: VenueInfo) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("場地資訊")
                .font(.title2.bold())
            Text(venue.name).font(.headline)
            Text(venue.address)
            Text(venue.parking).foregroundStyle(.secondary)
            Text(venue.metro).foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(18)
        .background(Color(nsColor: .windowBackgroundColor))
        .clipShape(RoundedRectangle(cornerRadius: 18))
    }

    private var attendanceSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("每堂上課紀錄")
                .font(.title2.bold())

            if let latestRecord = store.attendanceRecords.first {
                attendanceCard(for: latestRecord)

                let historyRecords = Array(store.attendanceRecords.dropFirst())
                if !historyRecords.isEmpty {
                    DisclosureGroup("查看較早上課紀錄（\(historyRecords.count) 筆）") {
                        VStack(alignment: .leading, spacing: 12) {
                            ForEach(historyRecords) { record in
                                attendanceCard(for: record)
                            }
                        }
                        .padding(.top, 10)
                    }
                }
            } else {
                Text("目前尚無上課紀錄。")
                    .foregroundStyle(.secondary)
            }
        }
    }

    @ViewBuilder
    private func attendanceCard(for record: AttendanceRecord) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(record.date).font(.headline)
                Spacer()
                Button("編輯") {
                    editingAttendance = record
                }
                .buttonStyle(.borderless)
                Button("刪除") {
                    deletingAttendance = record
                }
                .buttonStyle(.borderless)
                .foregroundStyle(.red)
                Text("\(record.attendeeCount) 人")
                    .foregroundStyle(.secondary)
            }
            let displayAttendees = record.attendeeDetails.map { detail in
                detail.cumulative.isEmpty ? detail.name : "\(detail.name) (\(detail.cumulative))"
            }.joined(separator: "、")
            Text(displayAttendees)
            if !record.note.isEmpty {
                Text(record.note)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(14)
        .background(Color(nsColor: .windowBackgroundColor))
        .clipShape(RoundedRectangle(cornerRadius: 14))
    }

    private var venueLedgerSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("場地費流水")
                .font(.title2.bold())

            if let latestRecord = store.venueLedger.first {
                venueLedgerCard(for: latestRecord)

                let historyRecords = Array(store.venueLedger.dropFirst())
                if !historyRecords.isEmpty {
                    DisclosureGroup("查看較早場地費紀錄（\(historyRecords.count) 筆）") {
                        VStack(alignment: .leading, spacing: 12) {
                            ForEach(historyRecords) { record in
                                venueLedgerCard(for: record)
                            }
                        }
                        .padding(.top, 10)
                    }
                }
            } else {
                Text("目前尚無場地費紀錄。")
                    .foregroundStyle(.secondary)
            }
        }
    }

    @ViewBuilder
    private func venueLedgerCard(for record: VenueLedgerRecord) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(record.date).font(.headline)
                Spacer()
                Button("編輯") {
                    editingLedger = record
                }
                .buttonStyle(.borderless)
                Button("刪除") {
                    deletingLedger = record
                }
                .buttonStyle(.borderless)
                .foregroundStyle(.red)
                Text(record.type)
                    .foregroundStyle(.secondary)
            }

            HStack(spacing: 16) {
                Text("金額：\(record.amount)")
                Text("餘額：\(record.balanceAfter)")
                if let headcount = record.headcount {
                    Text("人數：\(headcount)")
                }
            }
            .font(.subheadline)

            if !record.note.isEmpty {
                Text(record.note)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(14)
        .background(Color(nsColor: .windowBackgroundColor))
        .clipShape(RoundedRectangle(cornerRadius: 14))
    }

    private var roundsSection: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("學員最新一輪")
                .font(.title2.bold())

            if !activeRoundGroups.isEmpty {
                Text("目前有在上課")
                    .font(.headline)
                    .foregroundStyle(.secondary)

                ForEach(activeRoundGroups) { group in
                    VStack(alignment: .leading, spacing: 12) {
                        HStack {
                            Text(group.studentName)
                                .font(.headline)
                            Spacer()
                            if let latest = group.latestRound {
                                Text("\(latest.attendedCount)/8")
                                    .foregroundStyle(.secondary)
                            }
                        }

                        if let latest = group.latestRound {
                            RoundCard(title: "最新一輪", round: latest)
                        }

                        if !group.historyRounds.isEmpty {
                            DisclosureGroup("查看較早紀錄（\(group.historyRounds.count) 筆）") {
                                VStack(alignment: .leading, spacing: 12) {
                                    ForEach(group.historyRounds) { round in
                                        RoundCard(title: round.label, round: round)
                                    }
                                }
                                .padding(.top, 10)
                            }
                        }
                    }
                    .padding(16)
                    .background(Color(nsColor: .windowBackgroundColor))
                    .clipShape(RoundedRectangle(cornerRadius: 16))
                }
            }

            if !inactiveRoundGroups.isEmpty {
                Text("其他學員")
                    .font(.headline)
                    .foregroundStyle(.secondary)
                    .padding(.top, activeRoundGroups.isEmpty ? 0 : 8)

                ForEach(inactiveRoundGroups) { group in
                    DisclosureGroup {
                        VStack(alignment: .leading, spacing: 12) {
                            if let latest = group.latestRound {
                                RoundCard(title: "最新一輪", round: latest)
                            }

                            if !group.historyRounds.isEmpty {
                                Text("較早紀錄")
                                    .font(.headline)
                                    .padding(.top, 4)
                                ForEach(group.historyRounds) { round in
                                    RoundCard(title: round.label, round: round)
                                }
                            }
                        }
                        .padding(.top, 10)
                    } label: {
                        HStack {
                            Text(group.studentName)
                                .font(.headline)
                            Spacer()
                            if let latest = group.latestRound {
                                Text("\(latest.attendedCount)/8")
                                    .foregroundStyle(.secondary)
                            }
                        }
                    }
                    .padding(16)
                    .background(Color(nsColor: .windowBackgroundColor))
                    .clipShape(RoundedRectangle(cornerRadius: 16))
                }
            }
        }
    }

    private var sortedRoundGroups: [StudentRoundGroup] {
        store.roundGroups.sorted { lhs, rhs in
            comparePriority(lhs) < comparePriority(rhs)
        }
    }

    private var activeRoundGroups: [StudentRoundGroup] {
        sortedRoundGroups.filter { $0.latestRound?.isActive == true && $0.latestRound?.isExpired == false }
    }

    private var inactiveRoundGroups: [StudentRoundGroup] {
        sortedRoundGroups.filter { !($0.latestRound?.isActive == true && $0.latestRound?.isExpired == false) }
    }

    private func comparePriority(_ group: StudentRoundGroup) -> (Int, String) {
        guard let latest = group.latestRound else {
            return (4, group.studentName)
        }

        if latest.isActive && !latest.isExpired {
            return (0, group.studentName)
        }

        if latest.isFollowup && !latest.isExpired {
            return (1, group.studentName)
        }

        if latest.attendedCount >= 8 && !latest.isExpired {
            return (2, group.studentName)
        }

        if latest.isExpired {
            return (3, group.studentName)
        }

        return (2, group.studentName)
    }
}

private struct AddAliasRow: View {
    @EnvironmentObject private var store: AppStore
    @State private var alias = ""
    @State private var canonicalName = ""

    var body: some View {
        HStack(spacing: 12) {
            TextField("輸入別名，例如：邦寧大哥", text: $alias)
            Picker("正式學員", selection: $canonicalName) {
                Text("選擇正式學員").tag("")
                ForEach(store.roundGroups, id: \.studentName) { group in
                    Text(group.studentName).tag(group.studentName)
                }
            }
            .frame(maxWidth: 220)
            Button("新增別名") {
                Task {
                    let success = await store.addAlias(alias: alias, canonicalName: canonicalName)
                    if success {
                        alias = ""
                        canonicalName = ""
                    }
                }
            }
            .buttonStyle(.borderedProminent)
            .disabled(alias.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || canonicalName.isEmpty)
        }
    }
}

private struct AddAttendanceSheet: View {
    @EnvironmentObject private var store: AppStore
    @Environment(\.dismiss) private var dismiss

    let editingRecord: AttendanceRecord?
    @State private var date = Date()
    @State private var venue = "玫瑰客廳"
    @State private var attendeesText = ""
    @State private var note = ""
    @State private var isPreviewing = false

    init(editingRecord: AttendanceRecord? = nil) {
        self.editingRecord = editingRecord
        if let editingRecord {
            let formatter = DateFormatter()
            formatter.calendar = Calendar(identifier: .gregorian)
            formatter.locale = Locale(identifier: "zh_Hant_TW")
            formatter.dateFormat = "yyyy-MM-dd"
            _date = State(initialValue: formatter.date(from: editingRecord.date) ?? Date())
            _venue = State(initialValue: editingRecord.venue)
            _attendeesText = State(initialValue: editingRecord.attendees.joined(separator: "、"))
            _note = State(initialValue: editingRecord.note)
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            Text(editingRecord == nil ? "新增上課紀錄" : "編輯上課紀錄")
                .font(.title2.bold())

            DatePicker("日期", selection: $date, displayedComponents: .date)
            TextField("場地", text: $venue)
            VStack(alignment: .leading, spacing: 6) {
                Text("出席者")
                    .font(.headline)
                Text("請用頓號、逗號或換行分隔")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                TextEditor(text: $attendeesText)
                    .frame(minHeight: 140)
            }
            VStack(alignment: .leading, spacing: 6) {
                Text("備註")
                    .font(.headline)
                TextEditor(text: $note)
                    .frame(minHeight: 100)
            }

            VStack(alignment: .leading, spacing: 10) {
                HStack {
                    Button {
                        Task {
                            isPreviewing = true
                            _ = await store.previewAppleCEOAttendanceFromAPI(
                                date: date,
                                venue: venue,
                                attendeesText: attendeesText,
                                note: note
                            )
                            isPreviewing = false
                        }
                    } label: {
                        if isPreviewing {
                            ProgressView()
                                .controlSize(.small)
                            Text("預覽中")
                        } else {
                            Label("預覽 API 差異", systemImage: "doc.text.magnifyingglass")
                        }
                    }
                    .buttonStyle(.bordered)
                    .disabled(isPreviewing || attendeesText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)

                    Text(store.attendancePreviewStatus)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                if let preview = store.attendancePreviewResult {
                    AttendancePreviewPanel(preview: preview)
                }
            }

            HStack {
                Spacer()
                Button("取消") { dismiss() }
                Button("儲存") {
                    Task {
                        let success: Bool
                        if let editingRecord {
                            success = await store.updateAttendance(record: editingRecord, date: date, venue: venue, attendeesText: attendeesText, note: note)
                        } else {
                            success = await store.addAttendance(date: date, venue: venue, attendeesText: attendeesText, note: note)
                        }
                        if success {
                            dismiss()
                        }
                    }
                }
                .buttonStyle(.borderedProminent)
            }
        }
        .padding(24)
        .frame(width: 520)
        .onAppear {
            store.attendancePreviewResult = nil
            store.attendancePreviewStatus = "尚未產生預覽"
        }
    }
}

private struct AttendancePreviewPanel: View {
    let preview: AttendancePreviewResult

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 10) {
                Label("僅預覽", systemImage: "eye")
                Label("不寫入資料", systemImage: preview.willWrite ? "exclamationmark.triangle" : "lock")
                if preview.requiresHumanConfirmation {
                    Label("需人工確認", systemImage: "person.crop.circle.badge.checkmark")
                }
            }
            .font(.caption)
            .foregroundStyle(.secondary)

            Text("\(preview.proposedRecord.date)｜\(preview.proposedRecord.venue)｜\(preview.proposedRecord.attendeeCount) 人")
                .font(.subheadline.bold())

            if !preview.warnings.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    ForEach(preview.warnings, id: \.self) { warning in
                        Text(warning)
                    }
                }
                .font(.caption)
                .foregroundStyle(.orange)
            }

            if preview.affectedRounds.isEmpty {
                Text("沒有找到可影響的期別，請檢查學員姓名。")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else {
                ForEach(preview.affectedRounds) { round in
                    HStack {
                        VStack(alignment: .leading, spacing: 4) {
                            Text(round.studentName)
                                .font(.headline)
                            Text(round.after.label)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        Spacer()
                        Text("\(round.before.attendedCount)/8 → \(round.after.attendedCount)/8")
                            .font(.subheadline.bold())
                    }
                    .padding(10)
                    .background(Color(nsColor: .controlBackgroundColor))
                    .clipShape(RoundedRectangle(cornerRadius: 10))
                }
            }
        }
        .padding(12)
        .background(Color(nsColor: .windowBackgroundColor))
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }
}

private struct AddVenueLedgerSheet: View {
    @EnvironmentObject private var store: AppStore
    @Environment(\.dismiss) private var dismiss

    let editingRecord: VenueLedgerRecord?
    @State private var date = Date()
    @State private var type = "扣款"
    @State private var headcountText = ""
    @State private var amountText = ""
    @State private var note = ""

    private let types = ["扣款", "儲值", "調整"]

    init(editingRecord: VenueLedgerRecord? = nil) {
        self.editingRecord = editingRecord
        if let editingRecord {
            let formatter = DateFormatter()
            formatter.calendar = Calendar(identifier: .gregorian)
            formatter.locale = Locale(identifier: "zh_Hant_TW")
            formatter.dateFormat = "yyyy-MM-dd"
            _date = State(initialValue: formatter.date(from: editingRecord.date) ?? Date())
            _type = State(initialValue: editingRecord.type)
            _headcountText = State(initialValue: editingRecord.headcount.map(String.init) ?? "")
            _amountText = State(initialValue: String(abs(editingRecord.amount)))
            _note = State(initialValue: editingRecord.note)
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            Text(editingRecord == nil ? "新增場地費紀錄" : "編輯場地費紀錄")
                .font(.title2.bold())

            DatePicker("日期", selection: $date, displayedComponents: .date)
            Picker("類型", selection: $type) {
                ForEach(types, id: \.self) { item in
                    Text(item).tag(item)
                }
            }
            .pickerStyle(.segmented)

            TextField("人數（扣款時可填）", text: $headcountText)
            TextField("金額（可直接輸入；扣款填正數會自動轉負數）", text: $amountText)
            VStack(alignment: .leading, spacing: 6) {
                Text("備註")
                    .font(.headline)
                TextEditor(text: $note)
                    .frame(minHeight: 120)
            }

            if type == "扣款", let cost = store.venue?.costPerPerson {
                Text("目前場地每人費用：$\(cost)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            HStack {
                Spacer()
                Button("取消") { dismiss() }
                Button("儲存") {
                    Task {
                        let success: Bool
                        if let editingRecord {
                            success = await store.updateVenueLedger(
                                record: editingRecord,
                                date: date,
                                type: type,
                                headcountText: headcountText,
                                amountText: amountText,
                                note: note
                            )
                        } else {
                            success = await store.addVenueLedger(
                                date: date,
                                type: type,
                                headcountText: headcountText,
                                amountText: amountText,
                                note: note
                            )
                        }
                        if success {
                            dismiss()
                        }
                    }
                }
                .buttonStyle(.borderedProminent)
            }
        }
        .padding(24)
        .frame(width: 520)
    }
}

private struct SummaryCard: View {
    let title: String
    let value: String
    let note: String

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title)
                .font(.headline)
                .foregroundStyle(.secondary)
            Text(value)
                .font(.title2.bold())
            Text(note.isEmpty ? "目前沒有資料" : note)
                .font(.caption)
                .foregroundStyle(.secondary)
                .lineLimit(3)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(16)
        .background(Color(nsColor: .windowBackgroundColor))
        .clipShape(RoundedRectangle(cornerRadius: 16))
    }
}

private struct RoundCard: View {
    let title: String
    let round: StudentRoundRecord

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(title)
                    .font(.headline)
                Spacer()
                Text("\(round.attendedCount)/8")
                    .foregroundStyle(.secondary)
            }

            Text(round.paymentStatus)
                .foregroundStyle(.secondary)

            LazyVGrid(columns: [GridItem(.adaptive(minimum: 120), spacing: 8)], spacing: 8) {
                ForEach(Array(round.sessions.enumerated()), id: \.offset) { index, session in
                    Text("\(index + 1). \(session.isEmpty ? "未排" : session)")
                        .font(.caption)
                        .padding(.horizontal, 10)
                        .padding(.vertical, 8)
                        .background(Color.accentColor.opacity(session.isEmpty ? 0.08 : 0.18))
                        .clipShape(Capsule())
                }
            }

            if round.isFollowup {
                Text("接近完成，請先提醒續班")
                    .font(.caption.bold())
                    .foregroundStyle(.orange)
            }
            if round.attendedCount >= 8 {
                Text("已滿 8 堂，請通知續班")
                    .font(.caption.bold())
                    .foregroundStyle(.red)
            }
            if round.isExpired, let expiryDate = round.expiryDate {
                Text("已過期，四個月效期至 \(expiryDate)")
                    .font(.caption.bold())
                    .foregroundStyle(.red)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(14)
        .background(Color.accentColor.opacity(0.05))
        .clipShape(RoundedRectangle(cornerRadius: 14))
    }
}
