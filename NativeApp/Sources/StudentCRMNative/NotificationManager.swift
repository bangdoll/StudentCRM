import Foundation
import UserNotifications

@MainActor
final class NotificationManager {
    static let shared = NotificationManager()

    private let center = UNUserNotificationCenter.current()
    private let completedKey = "studentcrm.native.completed.notified"
    private let expiryKey = "studentcrm.native.expiry.notified"

    private init() {}

    func requestAuthorization() async {
        _ = try? await center.requestAuthorization(options: [.alert, .sound, .badge])
    }

    func refreshAppleCEONotifications(roundGroups: [StudentRoundGroup]) async {
        let completedNotified = Set(UserDefaults.standard.stringArray(forKey: completedKey) ?? [])
        let expiryNotified = Set(UserDefaults.standard.stringArray(forKey: expiryKey) ?? [])

        var nextCompleted = completedNotified
        var nextExpiry = expiryNotified

        for group in roundGroups {
            guard let latest = group.latestRound else { continue }

            if latest.attendedCount >= 8, !completedNotified.contains(latest.id) {
                await scheduleNotification(
                    id: "completed-\(latest.id)",
                    title: "蘋果總裁班已滿 8 堂",
                    body: "\(group.studentName) 已達 8/8，請通知續班。"
                )
                nextCompleted.insert(latest.id)
            }

            if let expiryDate = latest.expiryDate,
               latest.remainingCount > 0,
               !latest.isExpired,
               isWithinFourteenDays(expiryDate),
               !expiryNotified.contains(latest.id) {
                await scheduleNotification(
                    id: "expiry-\(latest.id)",
                    title: "蘋果總裁班即將到期",
                    body: "\(group.studentName) 的最新一輪將於 \(expiryDate) 到期。"
                )
                nextExpiry.insert(latest.id)
            }
        }

        UserDefaults.standard.set(Array(nextCompleted), forKey: completedKey)
        UserDefaults.standard.set(Array(nextExpiry), forKey: expiryKey)
    }

    private func scheduleNotification(id: String, title: String, body: String) async {
        let content = UNMutableNotificationContent()
        content.title = title
        content.body = body
        content.sound = .default

        let trigger = UNTimeIntervalNotificationTrigger(timeInterval: 1, repeats: false)
        let request = UNNotificationRequest(identifier: id, content: content, trigger: trigger)
        try? await center.add(request)
    }

    private func isWithinFourteenDays(_ dateString: String) -> Bool {
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.locale = Locale(identifier: "zh_Hant_TW")
        formatter.dateFormat = "yyyy-MM-dd"
        guard let date = formatter.date(from: dateString) else { return false }
        let days = Calendar.current.dateComponents([.day], from: Calendar.current.startOfDay(for: Date()), to: date).day ?? 999
        return days >= 0 && days <= 14
    }
}
