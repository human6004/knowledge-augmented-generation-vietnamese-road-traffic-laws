export type Role = "user" | "admin"
export type Session = { email: string; name: string; role: Role }
export const homeFor = (role: Role) => role === "admin" ? "/admin/dashboard" : "/chat"
