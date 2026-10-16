package db.migration;

import java.sql.SQLException;
import java.util.ArrayList;
import org.flywaydb.core.api.migration.BaseJavaMigration;
import org.flywaydb.core.api.migration.Context;

public class V4__account_police_role extends BaseJavaMigration {
    @Override public void migrate(Context context) throws Exception {
        var connection=context.getConnection();
        var metadata=connection.getMetaData();
        boolean mysql=metadata.getDatabaseProductName().equals("MySQL");
        var constraints=new ArrayList<String>();
        // V1 left this CHECK unnamed, so MySQL and H2 generate different names.
        try(var query=connection.prepareStatement("""
            SELECT tc.CONSTRAINT_NAME FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
            JOIN INFORMATION_SCHEMA.CHECK_CONSTRAINTS cc
              ON cc.CONSTRAINT_SCHEMA=tc.CONSTRAINT_SCHEMA AND cc.CONSTRAINT_NAME=tc.CONSTRAINT_NAME
            WHERE tc.CONSTRAINT_SCHEMA=? AND LOWER(tc.TABLE_NAME)='accounts'
              AND tc.CONSTRAINT_TYPE='CHECK' AND LOWER(cc.CHECK_CLAUSE) LIKE '%role%'
            """)) {
            query.setString(1,mysql?connection.getCatalog():connection.getSchema());
            try(var rows=query.executeQuery()) { while(rows.next()) constraints.add(rows.getString(1)); }
        }
        if(constraints.size()!=1) throw new SQLException("Expected one accounts.role CHECK constraint");
        String quote=metadata.getIdentifierQuoteString();
        String name=quote+constraints.getFirst().replace(quote,quote+quote)+quote;
        String drop="DROP "+(mysql?"CHECK ":"CONSTRAINT ")+name;
        String add="ADD CONSTRAINT accounts_role_check CHECK (role IN ('USER','POLICE','ADMIN'))";
        try(var statement=connection.createStatement()) {
            if(mysql) statement.execute("ALTER TABLE accounts "+drop+", "+add);
            else {
                statement.execute("ALTER TABLE accounts "+drop);
                statement.execute("ALTER TABLE accounts "+add);
            }
        }
    }
}
